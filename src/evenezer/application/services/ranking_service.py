import logging
from datetime import datetime

from evenezer.application.services.base_statistics_service import BaseStatisticsService
from evenezer.domain.statistics.models import (
    AnalyzedRankingItem,
    DailyMarketRanking,
    DailyMarketRankingAnalysis,
    MarketType,
    MonthlyMarketStats,
    RankingItem,
    SupplySubject,
)
from evenezer.infrastructure.persistence import netbuy_db_query
from evenezer.infrastructure.persistence.yearly_db_sync import YearlyDbSync

logger = logging.getLogger(__name__)

_COMBOS = [
    (MarketType.KOSPI, SupplySubject.FOREIGN),
    (MarketType.KOSPI, SupplySubject.INSTITUTION),
    (MarketType.KOSDAQ, SupplySubject.FOREIGN),
    (MarketType.KOSDAQ, SupplySubject.INSTITUTION),
]


class RankingService(BaseStatisticsService[DailyMarketRanking]):
    """거래일/월간 수급 순위 및 분석 전문 서비스.

    krx-auto-crawling이 발행하는 SQLite SSOT DB(market_data_{year}.db)를 로컬로
    구독해 조회한다 (docs/db_ssot_consumer_sync.md 참고).
    """

    def __init__(self, drive_adapter, folder_id, local_repository, db_sync: YearlyDbSync | None = None):
        super().__init__(drive_adapter, folder_id)
        self.repository = local_repository
        self.db_sync = db_sync or YearlyDbSync(
            drive_adapter=drive_adapter,
            data_root="data/statistics/netbuy/db",
            folder_name="sd",
            filename_for_year=lambda year: f"market_data_{year}.db",
            required_tables={"netbuy", "price_info"},
        )
        self._daily_cache = {}
        self._monthly_cache = {}

    def get_service_name(self) -> str:
        return "RankingService"

    async def get_daily_ranking(self, date_str: str, market: MarketType = None, subject: SupplySubject = None) -> list[DailyMarketRanking] | DailyMarketRanking | None:
        """로컬 저장소에서 당일 순위를 가져오고, 없으면 동기화합니다.

        기존 Facade와의 호환성을 위해 market, subject가 지정되면 단일 객체를 반환합니다.
        """
        cache_key = f"{date_str}_{market}_{subject}"
        if cache_key in self._daily_cache:
            return self._daily_cache[cache_key]

        if market and subject:
            res = self.repository.load_ranking(date_str, market, subject)
            if not res:
                await self.sync_data(date_str)
                res = self.repository.load_ranking(date_str, market, subject)
            if res:
                self._daily_cache[cache_key] = res
            return res

        rankings = self.repository.get_rankings(date_str)
        if not rankings:
            rankings = await self.sync_data(date_str)
        if rankings:
            self._daily_cache[cache_key] = rankings
        return rankings

    async def get_daily_summary(self, date: str) -> dict:
        """해당 날짜의 4가지 조합(코스피/코스닥 x 외국인/기관) 수급 분석 데이터를 요약하여 반환합니다."""
        summary = {
            "KOSPI": {
                "FOREIGN": await self.get_analyzed_ranking(date, MarketType.KOSPI, SupplySubject.FOREIGN),
                "INSTITUTION": await self.get_analyzed_ranking(date, MarketType.KOSPI, SupplySubject.INSTITUTION),
            },
            "KOSDAQ": {
                "FOREIGN": await self.get_analyzed_ranking(date, MarketType.KOSDAQ, SupplySubject.FOREIGN),
                "INSTITUTION": await self.get_analyzed_ranking(date, MarketType.KOSDAQ, SupplySubject.INSTITUTION),
            }
        }
        return summary

    async def get_monthly_ranking(self, month: str, market: MarketType, subject: SupplySubject) -> MonthlyMarketStats:
        """한 달간의 일별 데이터를 합산하여 월간 누적 수급 순위를 산출합니다."""
        cache_key = f"{month}_{market}_{subject}"
        if cache_key in self._monthly_cache:
            return self._monthly_cache[cache_key]

        available_dates = self.repository.list_available_dates(market, subject)
        target_dates = [d for d in available_dates if d.startswith(month)]

        if not target_dates:
            return MonthlyMarketStats(month=month, market=market, subject=subject, items=[])

        # 일별 데이터 로드
        daily_rankings = []
        for d in target_dates:
            ranking = self.repository.load_ranking(d, market, subject)
            if ranking:
                daily_rankings.append(ranking)

        if not daily_rankings:
            return MonthlyMarketStats(month=month, market=market, subject=subject, items=[])

        # 도메인 모델의 비즈니스 로직을 호출하여 합산 수행
        res = MonthlyMarketStats.aggregate_from_daily(month, daily_rankings)
        self._monthly_cache[cache_key] = res
        return res

    async def sync_data(self, date_str: str | None = None) -> list[DailyMarketRanking]:
        """SSOT DB를 최신 상태로 동기화하고, 아직 로컬에 없는 날짜만 순위표로 조립합니다.

        date_str가 주어지면 그 연도의 DB를, 없으면 올해 DB를 대상으로 한다.
        """
        try:
            if not self.drive_adapter:
                return []

            target_year = int(date_str[:4]) if date_str else datetime.now().year

            db_path = await self.db_sync.ensure_db(target_year)
            if not db_path:
                return self._get_fallback_rankings(date_str)

            # 로컬에 이미 존재하는 날짜는 건너뜀 (과거 데이터는 변경될 이유가 거의 없으므로
            # 신규 추가만 수행) - KOSPI/FOREIGN 조합을 대표값으로 삼는다(4개 조합은 항상
            # 함께 동기화되므로 하나만 확인해도 충분).
            existing_dates = set(self.repository.list_available_dates(MarketType.KOSPI, SupplySubject.FOREIGN))
            remote_dates = [d for d in netbuy_db_query.list_dates(db_path) if d not in existing_dates]

            all_rankings: list[DailyMarketRanking] = []
            for d in remote_dates:
                for market, subject in _COMBOS:
                    rows = netbuy_db_query.fetch_ranking_rows(db_path, market.value, subject.value, d)
                    if not rows:
                        continue
                    items = [
                        RankingItem(
                            rank=r["rank"],
                            name=r["stock_name"],
                            amount=r["net_buy_amount"],
                            ticker=r["stock_code"],
                            high_price_type=r["high_price_type"],
                        )
                        for r in rows
                    ]
                    ranking = DailyMarketRanking(date=d, market=market, subject=subject, items=items)
                    self.repository.save_daily_ranking(ranking)
                    all_rankings.append(ranking)

            if all_rankings:
                newly_synced_count = len(set(r.date for r in all_rankings))
                logger.info(f"[{self.get_service_name()}] 총 {newly_synced_count}일치 데이터가 새로 추가되었습니다.")
                if date_str:
                    return self.repository.get_rankings(date_str)
                return all_rankings

            return self._get_fallback_rankings(date_str)

        except Exception as e:
            logger.error(f"[{self.get_service_name()}] 순위 동기화 실패: {e}", exc_info=True)
            return []

    def _get_fallback_rankings(self, date_str: str | None) -> list[DailyMarketRanking]:
        """새로 동기화된 내용이 없는 상황에서, 최선의 로컬 순위 데이터를 조회하여 반환합니다."""
        if not date_str:
            dates = self.repository.list_available_dates(MarketType.KOSPI, SupplySubject.FOREIGN)
            if dates:
                date_str = dates[0]
        return self.repository.get_rankings(date_str) if date_str else []

    async def get_analyzed_ranking(self, date, market, subject) -> DailyMarketRankingAnalysis:
        """이전 거래일과 비교하여 순위 변동을 분석합니다."""
        raw = self.repository.load_ranking(date, market, subject)
        if not raw:
            return None

        available_dates = self.repository.list_available_dates(market, subject)
        try:
            current_idx = available_dates.index(date)
        except ValueError:
            analyzed_items = [AnalyzedRankingItem(**item.model_dump()) for item in raw.items]
            return DailyMarketRankingAnalysis(date=date, market=market, subject=subject, items=analyzed_items)

        # 이전 거래일 데이터와 대조 분석
        if current_idx + 1 < len(available_dates):
            prev_date = available_dates[current_idx + 1]
            prev_raw = self.repository.load_ranking(prev_date, market, subject)
            prev_map = {item.name: item.rank for item in prev_raw.items} if prev_raw else {}

            analyzed_items = []
            for item in raw.items:
                prev_rank = prev_map.get(item.name)
                analyzed_items.append(AnalyzedRankingItem(
                    **item.model_dump(),
                    prev_rank=prev_rank,
                    consecutive_days=await self._calculate_consecutive_days(
                        item.name, available_dates[current_idx:], market, subject, limit=11
                    )
                ))
            return DailyMarketRankingAnalysis(date=date, market=market, subject=subject, items=analyzed_items, previous_date=prev_date)

        return DailyMarketRankingAnalysis(date=date, market=market, subject=subject, items=[AnalyzedRankingItem(**it.model_dump()) for it in raw.items])

    async def _calculate_consecutive_days(self, name, dates, market, subject, limit: int = 30) -> int:
        """종목이 연속으로 순위권에 머문 일수를 계산합니다."""
        count = 0
        for d in dates:
            r = self.repository.load_ranking(d, market, subject)
            if r and any(it.name == name for it in r.items):
                count += 1
                if count >= limit:
                    break
            else:
                break
        return count
