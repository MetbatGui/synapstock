import io
import pandas as pd
from typing import List, Optional
from datetime import datetime
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

from synapstock.domain.statistics.models import (
    DailyMarketRanking, 
    MarketType, 
    SupplySubject, 
    RankingItem,
    MonthlyMarketStats,
    AnalyzedRankingItem,
    DailyMarketRankingAnalysis,
    CeilingItem,
    CeilingAnalysisReport
)

class ExcelStatisticsParser:
    """엑셀 파일을 파싱하여 통계 모델로 변환하는 유틸리티."""

    @staticmethod
    def _clean_stock_name(name: str) -> str:
        """종목명에서 '(쌍)', '(씽)', '(상)' 등의 노이즈 문자를 제거합니다.
        
        엑셀 수기 작성 시 '삼성전자 (쌍)' 처럼 쌍끌이를 표시하는 텍스트가 
        포함될 경우, 이를 순수 종목명 '삼성전자'로 원복하여 동일 종목으로 판정하기 위함입니다.
        """
        import re
        name_str = str(name).strip()
        # 종목명 뒤에 공백과 함께 (쌍), (씽), (상) 등이 괄호로 붙은 경우 제거
        cleaned = re.sub(r'\s*\([쌍씽상]\)$', '', name_str)
        return cleaned.strip()

    @staticmethod
    def parse_daily_ranking(
        content: bytes, 
        market: MarketType, 
        subject: SupplySubject, 
        date: str
    ) -> DailyMarketRanking:
        """일별 단일 수급 TOP 30 엑셀 파일을 파싱합니다.

        Args:
            content (bytes): 엑셀 파일의 바이너리 데이터.
            market (MarketType): 시장 유형 (KOSPI/KOSDAQ).
            subject (SupplySubject): 수급 주체 (FOREIGN/INSTITUTION).
            date (str): 데이터의 날짜 (YYYY-MM-DD 형식).

        Returns:
            DailyMarketRanking: 파싱된 일별 수급 순위 데이터 모델.
        """
        df = pd.read_excel(io.BytesIO(content))
        
        # 엑셀 구조 분석 결과 (20260406코스피외인기관.xlsx):
        # 컬럼 0: 종목명, 컬럼 1: 순매수금액
        items = []
        for i, row in df.iterrows():
            if i >= 30:
                break
            
            name = ExcelStatisticsParser._clean_stock_name(row.iloc[0])
            amount = int(row.iloc[1])
            
            items.append(RankingItem(
                rank=i + 1,
                name=name,
                amount=amount
            ))
            
        return DailyMarketRanking(
            date=date,
            market=market,
            subject=subject,
            items=items
        )

    @staticmethod
    def parse_summary_table(
        content: bytes,
        sheet_name: str,
        date: str
    ) -> List[DailyMarketRanking]:
        """종합 일별 수급 순위 정리표를 파싱합니다.

        하나의 시트에서 코스피 외인(E/F), 코스피 기관(I/J), 코스닥 외인(N/O), 코스닥 기관(R/S) 
        4가지 데이터 셋을 동시에 파싱하여 반환합니다.

        Args:
            content (bytes): 통합 엑셀 파일의 바이너리 데이터.
            sheet_name (str): 파싱할 타겟 시트명 (예: "0408").
            date (str): 파싱 데이터에 부여할 기준 날짜 (YYYY-MM-DD 형식).

        Returns:
            List[DailyMarketRanking]: 4개의 시장/주체 조합이 담긴 통계 리스트.
        """
        df = pd.read_excel(io.BytesIO(content), sheet_name=sheet_name, header=None)
        
        # 데이터 시작 행 (5행 -> index 4)
        start_row = 4
        num_items = 30
        
        # 4개 카테고리 정의 (순서: 종목명 컬럼 index, 금액 컬럼 index, 신고가 컬럼 index, 시장, 주체)
        configs = [
            (4, 5, 6, MarketType.KOSPI, SupplySubject.FOREIGN),     # E, F, G
            (8, 9, 10, MarketType.KOSPI, SupplySubject.INSTITUTION),  # I, J, K
            (13, 14, 15, MarketType.KOSDAQ, SupplySubject.FOREIGN),   # N, O, P
            (17, 18, 19, MarketType.KOSDAQ, SupplySubject.INSTITUTION) # R, S, T
        ]
        
        results = []
        for name_col, amt_col, high_col, market, subject in configs:
            items = []
            for i in range(num_items):
                row_idx = start_row + i
                if row_idx >= len(df): break
                
                name_raw = df.iloc[row_idx, name_col]
                amount_raw = df.iloc[row_idx, amt_col]
                high_val_raw = df.iloc[row_idx, high_col]
    
                # 빈 셀 체크
                if pd.isna(name_raw) or str(name_raw).strip() == "":
                    continue
                    
                name = ExcelStatisticsParser._clean_stock_name(name_raw)
                
                # 금액 정제 (숫자 외 문자 제거)
                amount = 0
                if not pd.isna(amount_raw):
                    if isinstance(amount_raw, (int, float)):
                        amount = int(amount_raw)
                    else:
                        cleaned = "".join(filter(str.isdigit, str(amount_raw)))
                        amount = int(cleaned) if cleaned else 0
    
                items.append(RankingItem(
                    rank=i + 1,
                    name=name,
                    amount=amount,
                    high_price_type=str(high_val_raw).strip() if not pd.isna(high_val_raw) and str(high_val_raw).strip() not in ('nan', '') else None
                ))
            
            results.append(DailyMarketRanking(
                date=date,
                market=market,
                subject=subject,
                items=items
            ))
            
        return results

    @staticmethod
    def parse_ceiling_report(
        content: bytes,
        title: str = "상한가 분석 리포트"
    ) -> CeilingAnalysisReport:
        """상한가 분석 엑셀 파일을 파싱하여 도메인 모델로 변환합니다.
        
        Args:
            content (bytes): 엑셀 파일 바이너리.
            title (str): 리포트 제목.

        Returns:
            CeilingAnalysisReport: 파싱된 상한가 분석 데이터.
        """
        import re
        df = pd.read_excel(io.BytesIO(content))
        
        # 1. 컬럼 구조 분석 (인덱스 기반 접근)
        col_names = df.columns.tolist()
        if len(col_names) < 3:
            raise ValueError(f"상한가 분석 엑셀 형식이 올바르지 않습니다. (컬럼 수: {len(col_names)})")
            
        name_col = col_names[0]
        tag_col = col_names[1]
        rate_col = col_names[-1]
        
        # YYMMDD 형식의 날짜 컬럼 추출 (가운데 위치한 6자리 숫자 컬럼들)
        date_cols = sorted([str(c) for c in col_names if str(c).isdigit() and len(str(c)) == 6])
        
        def parse_rate(val) -> float:
            if pd.isna(val): return 0.0
            if isinstance(val, (int, float)): return float(val)
            cleaned = re.sub(r'[^0-9.-]', '', str(val))
            return float(cleaned) if cleaned else 0.0

        def format_date(yymmdd: str) -> str:
            return f"20{yymmdd[:2]}-{yymmdd[2:4]}-{yymmdd[4:]}"

        # 2. 개별 항목 파싱
        ceiling_items = []
        for _, row in df.iterrows():
            name = str(row[name_col]).strip()
            # 빈 행 또는 잘못된 데이터 제외
            if not name or name.lower() in ('nan', 'none', ''):
                continue
                
            prices = []
            for d_col in date_cols:
                price_val = row[d_col]
                if not pd.isna(price_val):
                    try:
                        prices.append(int(price_val))
                    except (ValueError, TypeError):
                        continue
            
            ceiling_items.append(CeilingItem(
                name=ExcelStatisticsParser._clean_stock_name(name),
                entry_tag=str(row[tag_col]).strip() if not pd.isna(row[tag_col]) else "",
                closing_prices=prices,
                change_rate=parse_rate(row[rate_col]),
                is_completed=(len(prices) >= 10)
            ))
            
        # 3. 리포트 객체 생성
        return CeilingAnalysisReport(
            title=title,
            start_date=format_date(date_cols[0]) if date_cols else "",
            end_date=format_date(date_cols[-1]) if date_cols else "",
            items=ceiling_items,
            is_fully_collected=all(it.is_completed for it in ceiling_items) if ceiling_items else False
        )

    @staticmethod
    def parse_monthly_stats(
        content: bytes,
        market: MarketType,
        subject: SupplySubject,
        month: str
    ) -> MonthlyMarketStats:
        """월간 누적 수급 엑셀 파일(APR 시트 등)을 파싱합니다.

        Args:
            content (bytes): 월간 통계 엑셀 파일 바이너리 데이터.
            market (MarketType): 시장 유형.
            subject (SupplySubject): 수급 주체.
            month (str): 기준 월 (예: "2026-04").

        Returns:
            MonthlyMarketStats: 파싱된 월간 누적 통계 데이터.
        """
        xl = pd.ExcelFile(io.BytesIO(content))
        
        # 월 이름을 시트명에서 찾음 (예: "APR", "MAY" 또는 숫자 "04", "05")
        # 해당 월의 약어나 숫자가 포함된 시트를 우선 찾고 없으면 마지막 시트 사용
        target_sheet = None
        for name in xl.sheet_names:
            if month[-2:] in name or any(m in name.upper() for m in ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]):
                target_sheet = name
                break
        
        sheet_name = target_sheet or xl.sheet_names[-1]
        df = pd.read_excel(xl, sheet_name=sheet_name, header=None)
        
        # 데이터 시작 위치 탐색 (제목행 제외하고 실 데이터부터)
        # 보통 1~2행은 제목이나 범례일 가능성이 높음. "종목명" 키워드 위치를 찾거나 0행부터 탐색
        items = []
        start_row = 0
        for idx, row in df.iterrows():
            if "종목명" in str(row.values):
                start_row = idx + 1
                break
        
        # 순위 아이템 추출 (최대 100개 또는 데이터 끝까지)
        for i in range(start_row, len(df)):
            row = df.iloc[i]
            name_raw = row.iloc[0]
            
            # 빈 행이면 종료
            if pd.isna(name_raw) or str(name_raw).strip() in ("", "nan"):
                continue
                
            name = ExcelStatisticsParser._clean_stock_name(name_raw)
                
            # 금액 컬럼 (보통 1번 또는 2번 인덱스)
            amount_raw = row.iloc[1] if len(row) > 1 else 0
            amount = 0
            if not pd.isna(amount_raw):
                if isinstance(amount_raw, (int, float)):
                    amount = int(amount_raw)
                else:
                    cleaned = "".join(filter(str.isdigit, str(amount_raw)))
                    amount = int(cleaned) if cleaned else 0
            
            items.append(RankingItem(
                rank=len(items) + 1,
                name=name,
                amount=amount
            ))
            
            if len(items) >= 100: break
            
        return MonthlyMarketStats(
            month=month,
            market=market,
            subject=subject,
            items=items
        )

class StatisticsService:
    """통계 데이터를 관리하고 동기화하는 애플리케이션 서비스.
    
    Google Drive 등 원격 스토리지를 통해 통계 엑셀 데이터를 가져오고, 
    이를 로컬 저장소에 캐싱하며, 가공된 데이터를 분석하여 프론트엔드에 제공합니다.
    """

    def __init__(self, storage=None, repository=None, query_service=None):
        """StatisticsService 객체를 초기화합니다.

        Args:
            storage (IStoragePort, optional): 외부 스토리지(예: GoogleDriveAdapter) 어댑터 인스턴스.
            repository (IStatisticsRepository, optional): 통계 데이터를 저장/조회할 저장소 구현체.
            query_service (BoardQueryService, optional): 종목 정보 조회를 위한 서비스.
        """
        self._storage = storage
        self._repository = repository
        self._query_service = query_service
        self._parser = ExcelStatisticsParser()

    def _build_local_ticker_map(self) -> dict[str, str]:
        """시스템 내 모든 마인드맵 보드에서 종목명-티커 매핑을 빌드합니다."""
        ticker_map = {}
        if not self._query_service:
            return ticker_map
            
        try:
            # 모든 보드의 종목 정보를 평탄화하여 가져옴
            all_stocks = self._query_service.get_all_stocks_flat()
            for stock in all_stocks:
                name = stock.get('name')
                ticker = stock.get('ticker')
                if name and ticker:
                    ticker_map[name] = ticker
        except Exception as e:
            logger.error(f"[StatisticsService] 로컬 티커 맵 빌드 실패: {e}")
            
        return ticker_map

    def save_rankings(self, rankings: List[DailyMarketRanking]):
        """파싱된 랭킹 리스트를 애플리케이션 저장소에 영구 저장합니다.

        Args:
            rankings (List[DailyMarketRanking]): 저장할 일별 수급 순위 데이터 리스트.
        """
        if not self._repository:
            return
        for ranking in rankings:
            self._repository.save_daily_ranking(ranking)

    def get_daily_ranking(
        self, 
        date: str, 
        market: MarketType, 
        subject: SupplySubject
    ) -> Optional[DailyMarketRanking]:
        """특정 날짜의 수급 순위 데이터를 가져옵니다 (캐시 우선).

        로컬 레포지토리에 데이터가 있으면 반환하고, 없으면 Google Drive 스토리지에서 
        원본 종합 파일을 조회하여 파싱 후 자동 저장합니다.

        Args:
            date (str): 조회 날짜 (YYYY-MM-DD 형식).
            market (MarketType): 시장 유형.
            subject (SupplySubject): 수급 주체.

        Returns:
            Optional[DailyMarketRanking]: 조회된 랭킹 데이터. 존재하지 않거나 실패 시 None.
        """
        if self._repository:
            # fix: load_ranking으로 메서드명 정정
            cached = self._repository.load_ranking(date, market, subject)
            if cached:
                return cached
        
        # 저장소에 없으면 Google Drive에서 시도
        if self._storage:
            year = date[:4]
            date_clean = date.replace("-", "")
            filename = f"{year}년/일별수급정리표/{year}일별수급순위정리표.xlsx"
            
            content = self._storage.get_file(filename, folder="sd")
            if content:
                # 종합표로 가정하고 파싱
                # 날짜에 해당하는 시트명 (예: 0407)
                sheet_name = date_clean[-4:]
                try:
                    all_rankings = self._parser.parse_summary_table(content, sheet_name, date)
                    self.save_rankings(all_rankings) # 로컬 캐시 저장
                    
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.info(f"[StatisticsService] 구글 드라이브에서 데이터 다운로드 및 캐싱 완료 ({date})")
                    
                    for r in all_rankings:
                        if r.market == market and r.subject == subject:
                            return r
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"[StatisticsService] 파싱 실패 ({filename}, 시트:{sheet_name}): {e}", exc_info=True)
        
        return None

    def sync_from_storage(self, date_str: str) -> List[DailyMarketRanking]:
        """지정된 날짜의 통계 데이터를 클라우드 스토리지에서 수동으로 강제 동기화합니다.

        Args:
            date_str (str): 동기화할 기준 날짜 (YYYY-MM-DD 형식).

        Returns:
            List[DailyMarketRanking]: 성공적으로 동기화된 각 랭킹 데이터 리스트. 실패 시 빈 리스트.
        """
        if not self._storage:
            return []
            
        date_clean = date_str.replace("-", "")
        year = date_str[:4]
        filename = f"{year}년/일별수급정리표/{year}일별수급순위정리표.xlsx"
        
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[StatisticsService] 특정 날짜 동기화 시도: {date_str} ({filename})")
        
        content = self._storage.get_file(filename, folder="sd")
        if not content:
            logger.warning(f"[StatisticsService] 클라우드에서 파일을 찾을 수 없음: {filename}")
            return []
            
        sheet_name = date_clean[-4:]
        try:
            rankings = self._parser.parse_summary_table(content, sheet_name, date_str)
            self.save_rankings(rankings)
            logger.info(f"[StatisticsService] 동기화 및 캐싱 완료: {date_str}")
            return rankings
        except Exception as e:
            logger.error(f"[StatisticsService] 파싱 및 동기화 실패: {e}", exc_info=True)
            return []

    def sync_recent_data(self, limit: int = 5) -> int:
        """클라우드 스토리지를 탐색하여 최신 통계 데이터를 일괄 동기화합니다.

        당해년도 통합 엑셀 문서(`YYYY일별수급순위정리표.xlsx`) 하나를 읽어들인 뒤, 
        내부에 있는 최신 시트(`limit`개)들을 로컬로 일괄 파싱하여 저장합니다.

        Args:
            limit (int, optional): 동기화할 최대 최신 시트(일자) 수. 기본값 5.

        Returns:
            int: 성공적으로 동기화 처리된 일자(시트) 수.
        """
        if not self._storage:
            return 0
            
        import logging
        import datetime
        import pandas as pd
        import io
        
        logger = logging.getLogger(__name__)
        logger.info("[StatisticsService] 최근 수급 통계 데이터 탐색 시작 (Google Drive)")
        
        try:
            year = str(datetime.datetime.now().year)
            filename = f"{year}년/일별수급정리표/{year}일별수급순위정리표.xlsx"
            
            content = self._storage.get_file(filename, folder="sd")
            if not content:
                logger.warning(f"[StatisticsService] 클라우드 통합 파일을 찾을 수 없음: {filename}")
                return 0
                
            xl = pd.ExcelFile(io.BytesIO(content))
            sheet_names = xl.sheet_names
            
            # 4자리 숫자(MMDD)로 된 시트명만 필터링
            date_sheets = [s for s in sheet_names if len(s) == 4 and s.isdigit()]
            # 최신순 (문자열 내림차순) 정렬
            date_sheets.sort(reverse=True)
            
            target_sheets = date_sheets[:limit]
            
            synced_count = 0
            for sheet_name in target_sheets:
                # MM-DD 포맷을 YYYY-MM-DD로 변환
                formatted_date = f"{year}-{sheet_name[:2]}-{sheet_name[2:]}"
                
                try:
                    rankings = self._parser.parse_summary_table(content, sheet_name, formatted_date)
                    self.save_rankings(rankings)
                    synced_count += 1
                except Exception as e:
                    logger.error(f"[StatisticsService] {sheet_name} 시트 파싱 및 동기화 실패: {e}")
                    
            logger.info(f"[StatisticsService] 총 {synced_count}개 일자 동기화 완료")
            return synced_count
        except Exception as e:
            logger.error(f"[StatisticsService] 일괄 동기화 실패: {e}", exc_info=True)
            return 0

    def get_monthly_ranking(
        self,
        year_month: str,
        market: MarketType,
        subject: SupplySubject
    ) -> MonthlyMarketStats:
        """지정된 월의 일별 데이터를 모두 취합하여 누적 수급 TOP 30 랭킹을 산출합니다.
        
        Args:
            year_month (str): 취합할 대상 월 (예: "2026-04").
            market (MarketType): 시장.
            subject (SupplySubject): 수급 주체.
            
        Returns:
            MonthlyMarketStats: 합산 및 정렬이 완료된 월간 통계 데이터.
        """
        if not self._repository:
            return MonthlyMarketStats(month=year_month, market=market, subject=subject, items=[])
            
        available_dates = self._repository.list_available_dates(market, subject)
        target_dates = [d for d in available_dates if d.startswith(year_month)]
        
        if not target_dates:
            logger.warning(f"[StatisticsService] 월간 집계 실패: {year_month} ({market}, {subject})에 해당하는 데이터가 없습니다.")
            return MonthlyMarketStats(month=year_month, market=market, subject=subject, items=[])
            
        logger.info(f"[StatisticsService] {year_month} 월간 집계 시작 (대상 일수: {len(target_dates)}일)")
        accumulation = {}
        
        for date_str in target_dates:
            daily = self._repository.load_ranking(date_str, market, subject)
            if not daily:
                continue
            for item in daily.items:
                accumulation[item.name] = accumulation.get(item.name, 0) + item.amount
                
        # amount 기준 내림차순 정렬
        sorted_items = sorted(accumulation.items(), key=lambda x: x[1], reverse=True)[:30]
        
        # 성능 최적화: 로컬 티커 맵을 한 번만 빌드하여 재사용
        local_ticker_map = self._build_local_ticker_map()
        
        ranking_items = []
        for rank, (name, amount) in enumerate(sorted_items, 1):
            # 1순위: 로컬 마인드맵 보드에서 티커 찾기
            ticker = local_ticker_map.get(name)
            
            # 2순위: 보드에 없지만 이전에 검색된 적이 있는 경우 (필요 시 확장)
            # 현재는 속도를 위해 외부 검색은 배제하거나 검색 시도를 최소화함
            
            ranking_items.append(RankingItem(
                rank=rank,
                name=name,
                amount=amount,
                ticker=ticker,
                high_price_type=None
            ))
            
        logger.info(f"[StatisticsService] 월간 집계 완료: {year_month} ({len(ranking_items)}개 항목)")
            
        return MonthlyMarketStats(
            month=year_month,
            market=market,
            subject=subject,
            items=ranking_items
        )

    def get_analyzed_ranking(
        self, 
        date: str, 
        market: MarketType, 
        subject: SupplySubject
    ) -> Optional[DailyMarketRankingAnalysis]:
        """순위 변동 및 연속 등장 횟수가 포함된 분석 랭킹 데이터를 제공합니다.

        원시 매수 데이터(DailyMarketRanking)를 가져온 뒤, 직전 거래일의 정보 및 
        과거 10일간의 데이터를 대조하여 신규 등장 여부, 순위 증감, 며칠 연속 매수인지 등을 계산합니다.

        Args:
            date (str): 조회 기준 날짜.
            market (MarketType): 시장.
            subject (SupplySubject): 수급 주체.

        Returns:
            Optional[DailyMarketRankingAnalysis]: 분석 및 확장된 랭킹 DTO. 
                원시 데이터 자체가 없을 경우 None.
        """
        raw = self.get_daily_ranking(date, market, subject)
        if not raw or not self._repository:
            return None

        # 1. 가용한 날짜 목록 확보
        available_dates = self._repository.list_available_dates(market, subject)
        try:
            current_idx = available_dates.index(date)
        except ValueError:
            # 현재 날짜가 목록에 없으면(방금 파싱한 경우 등) 분석 없이 기본 반환
            analyzed_items = [AnalyzedRankingItem(**item.model_dump(), is_new=True) for item in raw.items]
            return DailyMarketRankingAnalysis(
                date=date, market=market, subject=subject, items=analyzed_items
            )

        # 2. 직전 거래일 대비 순위 변동 계산 데이터 준비
        prev_date = None
        prev_map = {}
        if current_idx + 1 < len(available_dates):
            prev_date = available_dates[current_idx + 1]
            prev_ranking = self._repository.load_ranking(prev_date, market, subject)
            if prev_ranking:
                prev_map = {item.name: item.rank for item in prev_ranking.items}

        # 3. 각 종목별 지표 계산
        lookback_limit = 10
        analyzed_items = []
        
        # 성능 최적화: 로컬 티커 맵 빌드
        local_ticker_map = self._build_local_ticker_map()
        
        for item in raw.items:
            # DTO 생성 (원본 필드 복사)
            analyzed = AnalyzedRankingItem(**item.model_dump())
            
            # 티커 매핑 주입
            analyzed.ticker = local_ticker_map.get(item.name)
            
            # 순위 변동 및 신규 진입 계산
            if item.name in prev_map:
                analyzed.prev_rank = prev_map[item.name]
                analyzed.rank_change = analyzed.prev_rank - analyzed.rank
                analyzed.is_new = False
            else:
                analyzed.is_new = True
                
            # 연속 등장 횟수 계산
            consecutive = 1
            for i in range(current_idx + 1, min(current_idx + 1 + lookback_limit, len(available_dates))):
                past_date = available_dates[i]
                past_ranking = self._repository.load_ranking(past_date, market, subject)
                if not past_ranking: break
                
                past_names = {p.name for p in past_ranking.items}
                if item.name in past_names:
                    consecutive += 1
                else:
                    break
            analyzed.consecutive_days = consecutive
            analyzed_items.append(analyzed)

        return DailyMarketRankingAnalysis(
            date=date,
            market=market,
            subject=subject,
            items=analyzed_items,
            previous_date=prev_date
        )
