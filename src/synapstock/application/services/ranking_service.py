import logging
import pandas as pd
import io
from synapstock.domain.statistics.models import DailyMarketRanking, DailyMarketRankingAnalysis, AnalyzedRankingItem
from synapstock.infrastructure.parsers.excel import SupplyDemandParser
from synapstock.application.services.base_statistics_service import BaseStatisticsService

logger = logging.getLogger(__name__)

class RankingService(BaseStatisticsService[DailyMarketRanking]):
    """거래일/월간 수급 순위 및 분석 전문 서비스."""

    def __init__(self, drive_adapter, folder_id, local_repository):
        super().__init__(drive_adapter, folder_id)
        self.repository = local_repository
        self.parser = SupplyDemandParser()

    def get_service_name(self) -> str:
        return "RankingService"

    def get_daily_ranking(self, date_str: str) -> list[DailyMarketRanking]:
        """로컬 저장소에서 당일 순위를 가져오고, 없으면 동기화합니다."""
        rankings = self.repository.get_rankings(date_str)
        if not rankings:
            return self.sync_data(date_str)
        return rankings

    def sync_data(self, date_str: str) -> list[DailyMarketRanking]:
        """엑셀 파일에서 순위 데이터를 파싱하고 동기화합니다."""
        try:
            if not self.drive_adapter:
                return []

            files = self.drive_adapter.list_files(self.folder_id)
            # 파일명 형식: "20260421" 포함된 파일 검색
            date_pure = date_str.replace("-", "")
            target_files = [f for f in files if date_pure in f["name"]]
            
            if not target_files:
                logger.warning(f"[RankingService] {date_str} 날짜의 순위 파일을 찾을 수 없습니다.")
                return []

            all_rankings = []
            for file_info in target_files:
                content = self.drive_adapter.download_file(file_info["id"])
                # 모든 시트 파싱
                sheets = pd.read_excel(io.BytesIO(content), sheet_name=None, header=None)
                for sheet_name in sheets.keys():
                    rankings = self.parser.parse_summary_table(content, sheet_name, date_str)
                    all_rankings.extend(rankings)
            
            self.repository.save_rankings(all_rankings)
            return all_rankings
        except Exception as e:
            logger.error(f"[RankingService] 순위 동기화 실패: {e}", exc_info=True)
            return []

    def get_analyzed_ranking(self, date, market, subject) -> DailyMarketRankingAnalysis:
        """이전 거래일과 비교하여 순위 변동을 분석합니다."""
        raw = self.repository.get_ranking_by_condition(date, market, subject)
        if not raw:
            return DailyMarketRankingAnalysis(date=date, market=market, subject=subject, items=[])

        available_dates = self.repository.get_available_dates(market, subject)
        try:
            current_idx = available_dates.index(date)
        except ValueError:
            analyzed_items = [AnalyzedRankingItem(**item.model_dump()) for item in raw.items]
            return DailyMarketRankingAnalysis(date=date, market=market, subject=subject, items=analyzed_items)

        # 이전 거래일 데이터와 대조 분석
        if current_idx + 1 < len(available_dates):
            prev_date = available_dates[current_idx + 1]
            prev_raw = self.repository.get_ranking_by_condition(prev_date, market, subject)
            prev_map = {item.name: item.rank for item in prev_raw.items} if prev_raw else {}
            
            analyzed_items = []
            for item in raw.items:
                prev_rank = prev_map.get(item.name)
                analyzed_items.append(AnalyzedRankingItem(
                    **item.model_dump(),
                    prev_rank=prev_rank,
                    consecutive_days=self._calculate_consecutive_days(item.name, available_dates[current_idx:], market, subject)
                ))
            return DailyMarketRankingAnalysis(date=date, market=market, subject=subject, items=analyzed_items, previous_date=prev_date)
        
        return DailyMarketRankingAnalysis(date=date, market=market, subject=subject, items=[AnalyzedRankingItem(**it.model_dump()) for it in raw.items])

    def _calculate_consecutive_days(self, name, dates, market, subject) -> int:
        """종목이 연속으로 순위권에 머문 일수를 계산합니다."""
        count = 0
        for d in dates:
            r = self.repository.get_ranking_by_condition(d, market, subject)
            if r and any(it.name == name for it in r.items):
                count += 1
            else:
                break
        return count
