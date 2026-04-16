import datetime
import time
import logging
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

    def sync_daily_data(self, date_str: Optional[str] = None) -> bool:
        """특정 날짜(기본값 당일)의 모든 시장 데이터를 수집하여 저장한다.
        수집할 데이터가 없거나 휴장일인 경우 False를 반환한다.
        """
        if not date_str:
            date_str = datetime.date.today().strftime("%Y%m%d")
            
        logger.info(f"[MarketDataService] 데이터 동기화 시작: {date_str}")

        # 1. 전종목 시세/거래대금 수집 (KOSPI, KOSDAQ)
        markets = ["STK", "KSQ"]
        valid_date = False
        
        for mkt in markets:
            prices = self.krx.fetch_market_prices(mkt, date_str)
            # 데이터가 비어있다면 휴장일일 가능성이 높음
            if prices and len(prices) > 0:
                self.repo.save_raw_data(date_str, f"prices_{mkt}", prices)
                logger.info(f"[MarketDataService] {mkt} 시세 저장 완료")
                valid_date = True
            else:
                logger.warning(f"[MarketDataService] {date_str} {mkt} 시세 데이터가 없습니다. (휴장일 가능성)")

        if not valid_date:
            logger.info(f"[MarketDataService] {date_str}는 휴장일로 판단되어 수집을 중단합니다.")
            return False

        # 2. 전종목 수급 수집 (기관, 외인)
        investors = {"7050": "INSTITUTION", "9000": "FOREIGN"}
        for mkt in markets:
            for inv_cd, inv_name in investors.items():
                excel_bytes = self.krx.fetch_net_purchase_data(mkt, inv_cd, date_str)
                if excel_bytes:
                    try:
                        df = pd.read_excel(io.BytesIO(excel_bytes))
                        data_list = df.to_dict(orient='records')
                        if len(data_list) > 0:
                            self.repo.save_raw_data(date_str, f"supply_{mkt}_{inv_name}", data_list)
                            logger.info(f"[MarketDataService] {mkt} {inv_name} 수급 저장 완료")
                    except Exception as e:
                        logger.error(f"[MarketDataService] {mkt} {inv_name} 수급 데이터 변환 오류: {e}")

        # 3. 시장 전체 투자자별 거래 실적 요약 수집 (신규 추가)
        market_performances = {}
        for mkt in markets:
            perf_bytes = self.krx.fetch_investor_trading_data(mkt, date_str)
            if perf_bytes:
                try:
                    df_perf = pd.read_excel(io.BytesIO(perf_bytes))
                    if len(df_perf) < 8: continue # 최소한의 행 확인

                    summary = {"market": mkt, "date": date_str}
                    
                    # 인덱스 기반 정밀 추출 (인코딩 무관)
                    # Row 4: 외국인, Row 7: 기관합계, Row 9: 전체 합계
                    # Col 6: 순매수대금, Col 5: 거래대금(매수)
                    
                    # 1. 외국인 순매수
                    foreign_row = df_perf.iloc[4] if len(df_perf) > 4 else None
                    if foreign_row is not None:
                        summary["ForeignNetBuy"] = int(foreign_row.iloc[6])

                    # 2. 기관합계 순매수
                    inst_row = df_perf.iloc[7] if len(df_perf) > 7 else None
                    if inst_row is not None:
                        summary["InstitutionalNetBuy"] = int(inst_row.iloc[6])

                    # 3. 전체 거래대금 (합계 행의 매수거래대금 활용)
                    total_row = df_perf.iloc[df_perf.index[-1]] # 마지막 행이 보통 전체 합계
                    summary["TotalTradeValue"] = int(total_row.iloc[5])
                        
                    market_performances[mkt] = summary
                    logger.info(f"[MarketDataService] {mkt} 시장 요약 데이터(인덱스 기반) 추출 완료")
                except Exception as e:
                    logger.error(f"[MarketDataService] {mkt} 시장 요약 데이터 파싱 오류: {e}")

        if market_performances:
            self.repo.save_raw_data(date_str, "market_performance", market_performances)
            logger.info(f"[MarketDataService] {date_str} 시장 통합 요약 정보 저장 완료")

        logger.info(f"[MarketDataService] {date_str} 데이터 동기화 완료")
        return True

    def sync_range_data(self, start_date_str: str, end_date_str: str = None):
        """지정된 범위의 날짜들에 대해 순차적으로 데이터를 동기화한다."""
        start_date = datetime.datetime.strptime(start_date_str, "%Y%m%d").date()
        if not end_date_str:
            end_date = datetime.date.today()
        else:
            end_date = datetime.datetime.strptime(end_date_str, "%Y%m%d").date()

        current_date = start_date
        while current_date <= end_date:
            # 주말 제외 (0:월, 1:화, ..., 4:금, 5:토, 6:일)
            if current_date.weekday() < 5:
                curr_str = current_date.strftime("%Y%m%d")
                
                # 중복 체크: 모든 필수 파일이 이미 존재하는지 확인
                is_all_exists = True
                for mkt in ["STK", "KSQ"]:
                    if not self.repo.exists(curr_str, f"prices_{mkt}"): is_all_exists = False; break
                    if not self.repo.exists(curr_str, f"supply_{mkt}_FOREIGN"): is_all_exists = False; break
                    if not self.repo.exists(curr_str, f"supply_{mkt}_INSTITUTION"): is_all_exists = False; break
                
                if is_all_exists:
                    logger.info(f"[MarketDataService] {curr_str} 데이터가 이미 존재하여 건너뜁니다.")
                else:
                    try:
                        success = self.sync_daily_data(curr_str)
                        if success:
                            # 성공 시에만 대기 (휴장일 스킵 시에는 대기 없이 진행)
                            time.sleep(1.5)
                        else:
                            logger.info(f"[MarketDataService] {curr_str} 일은 건너뜁니다.")
                    except Exception as e:
                        logger.error(f"[MarketDataService] {curr_str} 동기화 중 오류 발생: {e}")

            current_date += datetime.timedelta(days=1)
        
        logger.info(f"[MarketDataService] {start_date_str} ~ {end_date_str or '오늘'} 범위 수집 완료")

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
