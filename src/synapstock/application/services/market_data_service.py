import logging
import datetime
import io
import pandas as pd
from typing import List, Dict, Optional
from synapstock.domain.ports import KrxDataPort, PriceDataPort
from synapstock.infrastructure.adapters.local.market_data_repo import LocalMarketDataRepository

logger = logging.getLogger(__name__)

class MarketDataService:
    """시장 데이터 수집 및 파생 지표 분석을 담당하는 서비스."""

    def __init__(
        self, 
        krx_adapter: KrxDataPort, 
        repository: LocalMarketDataRepository
    ):
        self.krx = krx_adapter
        self.repo = repository

    def sync_daily_data(self, date_str: Optional[str] = None):
        """특정 날짜(기본값 당일)의 모든 시장 데이터를 수집하여 저장한다."""
        if not date_str:
            date_str = datetime.date.today().strftime("%Y%m%d")
            
        logger.info(f"[MarketDataService] 데이터 동기화 시작: {date_str}")

        # 1. 전종목 시세/거래대금 수집 (KOSPI, KOSDAQ)
        markets = ["STK", "KSQ"]
        for mkt in markets:
            prices = self.krx.fetch_market_prices(mkt, date_str)
            if prices:
                self.repo.save_raw_data(date_str, f"prices_{mkt}", prices)
                logger.info(f"[MarketDataService] {mkt} 시세 저장 완료")

        # 2. 전종목 수급 수집 (기관, 외인)
        # 7050: 기관, 9000: 외국인(사용자 파라미터 기준)
        investors = {"7050": "INSTITUTION", "9000": "FOREIGN"}
        for mkt in markets:
            for inv_cd, inv_name in investors.items():
                excel_bytes = self.krx.fetch_net_purchase_data(mkt, inv_cd, date_str)
                if excel_bytes:
                    # 엑셀을 JSON 리스트로 변환하여 저장 (나중에 쓰기 편하게)
                    df = pd.read_excel(io.BytesIO(excel_bytes))
                    data_list = df.to_dict(orient='records')
                    self.repo.save_raw_data(date_str, f"supply_{mkt}_{inv_name}", data_list)
                    logger.info(f"[MarketDataService] {mkt} {inv_name} 수급 저장 완료")

        logger.info(f"[MarketDataService] {date_str} 데이터 동기화 완료")

    def get_market_analysis(self, date_str: str) -> pd.DataFrame:
        """수집된 데이터를 결합하여 파생 지표가 포함된 분석 데이터프레임을 반환한다."""
        # 1. 데이터 로드
        mkt_dfs = []
        for mkt in ["STK", "KSQ"]:
            prices = self.repo.load_raw_data(date_str, f"prices_{mkt}")
            if not prices: continue
            
            df_price = pd.DataFrame(prices)
            
            # 수급 데이터 결합 (외인/기관)
            for inv_name in ["INSTITUTION", "FOREIGN"]:
                supply = self.repo.load_raw_data(date_str, f"supply_{mkt}_{inv_name}")
                if supply:
                    df_supply = pd.DataFrame(supply)
                    # 종목코드 기준으로 Join (KRX 엑셀은 '종목코드' 컬럼 사용)
                    # 시세 데이터는 'ISU_SRT_CD' 또는 'MKTSC_ITM_ID' 등 사용 (API마다 다름)
                    # 여기선 티커를 맞추는 전처리가 필요함
                    pass

            mkt_dfs.append(df_price)

        if not mkt_dfs:
            return pd.DataFrame()

        full_df = pd.concat(mkt_dfs)
        
        # 2. 파생 지표 처리 (예: 거래대금 순위)
        if 'AMT_TRD' in full_df.columns:
            full_df['AMT_TRD'] = pd.to_numeric(full_df['AMT_TRD'].str.replace(',', ''), errors='coerce')
            full_df['AMT_RANK'] = full_df['AMT_TRD'].rank(ascending=False)
            
        return full_df
