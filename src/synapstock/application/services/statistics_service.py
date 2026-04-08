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
        """일별 수급 TOP 30 엑셀 파싱."""
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
        """종합 일별 수급 순위 정리표 파싱 (E5, H5, N5, R5 구조)."""
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
        """월간 누적 수급 엑셀 파싱 (APR 시트 등)."""
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
    """통계 데이터를 관리하고 동기화하는 애플리케이션 서비스."""

    def __init__(self, storage=None, repository=None):
        self._storage = storage
        self._repository = repository  # LocalStatisticsRepository
        self._parser = ExcelStatisticsParser()

    def save_rankings(self, rankings: List[DailyMarketRanking]):
        """파싱된 랭킹 리스트를 저장소에 영구 저장한다."""
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
        """특정일의 수급 순위를 가져온다 (캐시 우선)."""
        if self._repository:
            # fix: load_ranking으로 메서드명 정정
            cached = self._repository.load_ranking(date, market, subject)
            if cached:
                return cached
        
        # 저장소에 없으면 Google Drive에서 시도
        if self._storage:
            # 파일명 규칙: daily_ranking_YYYYMMDD.xlsx (종합표 기준)
            date_clean = date.replace("-", "")
            filename = f"daily_ranking_{date_clean}.xlsx"
            
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
                    logger.error(f"[StatisticsService] 파싱 실패 ({filename}): {e}", exc_info=True)
        
        return None

    def sync_from_storage(self, date_str: str) -> List[DailyMarketRanking]:
        """Google Drive에서 특정 날짜의 데이터를 가져와 로컬에 동기화한다."""
        if not self._storage:
            return []
            
        date_clean = date_str.replace("-", "")
        filename = f"daily_ranking_{date_clean}.xlsx"
        
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
        """구글 드라이브의 최근 엑셀 파일들을 탐색하여 로컬에 동기화한다."""
        if not self._storage:
            return 0
            
        import logging
        logger = logging.getLogger(__name__)
        logger.info("[StatisticsService] 최근 수급 통계 데이터 탐색 시작 (Google Drive)")
        
        try:
            # 1. 파일 목록 조회 (sd 폴더의 루트)
            files = self._storage.list_files_in_folder("", folder="sd")
            
            # daily_ranking_YYYYMMDD.xlsx 패턴 필터링
            target_files = []
            for f in files:
                name = f['name']
                if name.startswith("daily_ranking_") and name.endswith(".xlsx"):
                    date_part = name.replace("daily_ranking_", "").replace(".xlsx", "")
                    if len(date_part) == 8:
                        target_files.append((name, date_part))
            
            # 최신순 정렬
            target_files.sort(key=lambda x: x[1], reverse=True)
            
            # 2. 로컬에 없는 파일 위주로 동기화 (최대 limit개)
            synced_count = 0
            for filename, date_clean in target_files[:limit]:
                formatted_date = f"{date_clean[:4]}-{date_clean[4:6]}-{date_clean[6:]}"
                
                # 모든 주체/시장 조합이 로컬에 있는지 확인하기엔 번거로우므로, 일단 폴더 내 파일 존재 여부로 판단
                # (Repository를 통해 체크하는 것이 더 정확하지만, 단순화를 위해 매번 시도하거나 시트 존재 확인)
                self.sync_from_storage(formatted_date)
                synced_count += 1
                
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
        """순위 변동 및 연속 등장 정보가 포함된 분석된 랭킹(DTO)을 반환한다."""
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
