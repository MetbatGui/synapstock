import logging
from typing import Any, cast

from synapstock.application.services.ceiling_analysis_service import CeilingAnalysisService
from synapstock.application.services.disclosure_analysis_service import DisclosureAnalysisService
from synapstock.application.services.new_listing_service import NewListingService
from synapstock.application.services.ranking_service import RankingService
from synapstock.domain.statistics.models import (
    CeilingAnalysisReport,
    DailyMarketRanking,
    DailyMarketRankingAnalysis,
    NewListing,
)

logger = logging.getLogger(__name__)

class StatisticsService:
    """통계 분석 도메인의 모든 기능을 조율하는 Facade 서비스.
    
    기존의 모든 의존성(레포지토리 등)을 유지하며, 실제 로직은 전문 서비스로 위임합니다.
    """

    def __init__(
        self,
        storage: Any = None,
        repository: Any = None,
        query_service: Any = None,
        ceiling_repository: Any = None,
        capital_increase_repository: Any = None,
        bonus_issue_repository: Any = None,
        convertible_bond_repository: Any = None,
        bw_repository: Any = None,
        market_data_service: Any = None,
    ):
        self._storage = storage
        self._query_service = query_service

        # 도메인 서비스 초기화 및 의존성 주입
        self.ranking_svc = RankingService(storage, "", repository)
        self.ceiling_svc = CeilingAnalysisService(storage, "", ceiling_repository)
        self.ipo_svc = NewListingService(storage, "", repository) # IPO는 기본 레포지토리 공유 혹은 별도 지정

        # 공시 서비스는 복합 레포지토리가 필요하므로 Facade에서 조율하거나 래퍼 전달
        # DisclosureAnalysisService 내부에서 repository들을 타입별로 처리할 수 있도록 래퍼 또는 직접 매핑 필요
        class MultiRepoWrapper:
            def __init__(self, ci, bi, cb, bw):
                self.get_capital_increase_data = ci.load_data if ci else lambda x: []
                self.save_capital_increase_data = ci.save_data if ci else lambda x: None
                self.get_bonus_issue_data = bi.load_data if bi else lambda x: []
                self.save_bonus_issue_data = bi.save_data if bi else lambda x: None
                self.get_convertible_bond_data = cb.load_data if cb else lambda x: []
                self.save_convertible_bond_data = cb.save_data if cb else lambda x: None
                self.get_bw_data = bw.load_data if bw else lambda x: []
                self.save_bw_data = bw.save_data if bw else lambda x: None

        disclosure_repo = MultiRepoWrapper(
            capital_increase_repository, bonus_issue_repository,
            convertible_bond_repository, bw_repository
        )
        self.disclosure_svc = DisclosureAnalysisService(storage, "", disclosure_repo)

    def _build_local_ticker_map(self) -> dict[str, str]:
        """마인드맵 보드의 모든 종목-티커 매핑을 가져옵니다."""
        ticker_map: dict[str, str] = {}
        if not self._query_service:
            return ticker_map
        try:
            all_stocks = cast(list[dict], self._query_service.get_all_stocks_flat())
            for stock in all_stocks:
                name = stock.get("name")
                ticker = stock.get("ticker")
                if name and ticker:
                    ticker_map[name] = ticker
                    aliases = stock.get("aliases", [])
                    for alias in aliases:
                        if alias: ticker_map[alias] = ticker
            return ticker_map
        except Exception as e:
            logger.error(f"[StatisticsService] 티커 맵 생성 실패: {e}")
            return ticker_map

    def _enrich_tickers(self, items: list) -> list:
        """아이템 리스트의 티커 정보를 보강합니다."""
        ticker_map = self._build_local_ticker_map()
        for item in items:
            if hasattr(item, "ticker") and not item.ticker and item.name in ticker_map:
                item.ticker = ticker_map[item.name]
        return items

    # --- 수급 순위 (Ranking) ---
    def get_daily_ranking(self, date_str: str) -> list[DailyMarketRanking]:
        return self.ranking_svc.get_daily_ranking(date_str)

    def save_rankings(self, rankings: list[DailyMarketRanking]):
        """랭킹 데이터 리스트를 저장합니다."""
        for r in rankings:
            self.ranking_svc.repository.save_daily_ranking(r)

    def get_analyzed_ranking(self, date: str, market: Any, subject: Any) -> DailyMarketRankingAnalysis:
        return self.ranking_svc.get_analyzed_ranking(date, market, subject)

    def get_daily_summary(self, date: str) -> dict:
        return self.ranking_svc.get_daily_summary(date)

    def get_monthly_ranking(self, month: str, market: Any, subject: Any) -> Any:
        result = self.ranking_svc.get_monthly_ranking(month, market, subject)
        if result and result.items:
            self._enrich_tickers(result.items)
        return result

    # --- 상한가 분석 (Price Stats) ---
    def get_ceiling_analysis(self, date: str, force_sync: bool = False) -> CeilingAnalysisReport | None:
        return self.ceiling_svc.get_ceiling_analysis(date, force_sync=force_sync)

    def list_available_ceiling_years(self) -> list[str]:
        return self.ceiling_svc.list_available_years()

    def list_available_ceiling_dates(self, year: str) -> list[str]:
        return self.ceiling_svc.list_available_dates(year)

    # --- 공시 분석 (Disclosure) ---
    def get_capital_increase_data(self, force_sync: bool = False, year: str = "2026") -> list:
        items = self.disclosure_svc.get_data("capital_increase", year, force_sync=force_sync)
        return self._enrich_tickers(items)

    def get_bonus_issue_data(self, force_sync: bool = False, year: str = "2026") -> list:
        items = self.disclosure_svc.get_data("bonus_issue", year, force_sync=force_sync)
        return self._enrich_tickers(items)

    def get_convertible_bond_data(self, force_sync: bool = False, year: str = "2026") -> list:
        items = self.disclosure_svc.get_data("cb", year, force_sync=force_sync)
        return self._enrich_tickers(items)

    def get_bw_data(self, force_sync: bool = False, year: str = "2026") -> list:
        items = self.disclosure_svc.get_data("bw", year, force_sync=force_sync)
        return self._enrich_tickers(items)

    # --- 신규 상장 (IPO) ---
    def get_new_listing_data(self, force_sync: bool = False, year: str = "2026") -> list[NewListing]:
        items = self.ipo_svc.get_data(year, force_sync=force_sync)
        return self._enrich_tickers(items)

    # --- 동기화 명령 (Sync) ---
    def sync_new_listing_data(self, year: str = "2026") -> list[NewListing]:
        items = self.ipo_svc.sync_data(year)
        return self._enrich_tickers(items)

    def sync_capital_increase_data(self, year: str = "2026") -> list:
        items = self.disclosure_svc.sync_data("capital_increase", year)
        return self._enrich_tickers(items)

    def sync_recent_data(self, limit: int = 5) -> int:
        """최근 랭킹 데이터를 동기화합니다."""
        # RankingService.sync_data는 단일 날짜 또는 최신 날짜 동기화이므로
        # 여러 날짜를 하려면 별도 루프 필요할 수 있음.
        # 여기서는 단순 위임 또는 최근 N일치 처리 로직 구현.
        # 기존 router는 count를 기대함.
        res = self.ranking_svc.sync_data()
        return len(res) if res else 0

    def list_available_dates(self, market: Any, subject: Any) -> list[str]:
        return self.ranking_svc.repository.list_available_dates(market, subject)

    @property
    def _repository(self):
        """하위 호환성을 위해 랭킹 레포지토리를 반환합니다."""
        return self.ranking_svc.repository
