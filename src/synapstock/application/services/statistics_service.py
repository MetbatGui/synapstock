import io
import pandas as pd
from typing import List, Optional
from datetime import datetime
from pathlib import Path

from synapstock.domain.statistics.models import (
    DailyMarketRanking, 
    MarketType, 
    SupplySubject, 
    RankingItem,
    MonthlyMarketStats,
    AnalyzedRankingItem,
    DailyMarketRankingAnalysis
)

class ExcelStatisticsParser:
    """엑셀 파일을 파싱하여 통계 모델로 변환하는 유틸리티."""

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
            
            name = str(row.iloc[0]).strip()
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
        
        # 4개 카테고리 정의 (순서: 종목명 컬럼 index, 금액 컬럼 index, 시장, 주체)
        configs = [
            (4, 5, MarketType.KOSPI, SupplySubject.FOREIGN),     # E, F
            (8, 9, MarketType.KOSPI, SupplySubject.INSTITUTION),  # I, J
            (13, 14, MarketType.KOSDAQ, SupplySubject.FOREIGN),   # N, O
            (17, 18, MarketType.KOSDAQ, SupplySubject.INSTITUTION) # R, S
        ]
        
        results = []
        for name_col, amt_col, market, subject in configs:
            items = []
            for i in range(num_items):
                row_idx = start_row + i
                if row_idx >= len(df): break
                
                name = df.iloc[row_idx, name_col]
                amount_raw = df.iloc[row_idx, amt_col]
    
                # 빈 셀 체크
                if pd.isna(name) or str(name).strip() == "":
                    continue
                
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
                    name=str(name).strip(),
                    amount=amount
                ))
            
            results.append(DailyMarketRanking(
                date=date,
                market=market,
                subject=subject,
                items=items
            ))
            
        return results

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
            name = str(row.iloc[0]).strip() if not pd.isna(row.iloc[0]) else ""
            
            # 빈 행이면 종료
            if not name or name == "nan":
                continue
                
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

    def __init__(self, storage=None, repository=None):
        """StatisticsService 객체를 초기화합니다.

        Args:
            storage (IStoragePort, optional): 외부 스토리지(예: GoogleDriveAdapter) 어댑터 인스턴스.
            repository (IStatisticsRepository, optional): 통계 데이터를 저장/조회할 저장소 구현체.
        """
        self._storage = storage
        self._repository = repository
        self._parser = ExcelStatisticsParser()

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
        
        for item in raw.items:
            # DTO 생성 (원본 필드 복사)
            analyzed = AnalyzedRankingItem(**item.model_dump())
            
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
