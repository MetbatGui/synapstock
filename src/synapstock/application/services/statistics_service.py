import json
import logging
from datetime import UTC, datetime
from pathlib import Path
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
        manifest_path: Path = Path("data/board/board_sync_manifest.json"),
        virtual_board_path: Path = Path("data/board/virtual_신규상장주.json"),
    ):
        self._storage = storage
        self._query_service = query_service
        self._manifest_path = manifest_path
        self._virtual_board_path = virtual_board_path

        # 도메인 서비스 초기화 및 의존성 주입
        self.ranking_svc = RankingService(storage, "", repository)
        self.ceiling_svc = CeilingAnalysisService(storage, "", ceiling_repository)
        self.ipo_svc = NewListingService(storage, "", repository)  # IPO는 기본 레포지토리 공유 혹은 별도 지정

        # 공시 서비스는 복합 레포지토리가 필요하므로 Facade에서 조율하거나 래퍼 전달
        # DisclosureAnalysisService 내부에서 repository들을 타입별로 처리할 수 있도록 래퍼 또는 직접 매핑 필요
        class MultiRepoWrapper:
            def __init__(self, ci, bi, cb, bw):
                self.get_capital_increase_data = (lambda year=None: ci.load_data()) if ci else lambda x: []
                self.save_capital_increase_data = ci.save_data if ci else lambda x: None
                self.get_bonus_issue_data = (lambda year=None: bi.load_data()) if bi else lambda x: []
                self.save_bonus_issue_data = bi.save_data if bi else lambda x: None
                self.get_convertible_bond_data = (lambda year=None: cb.load_data()) if cb else lambda x: []
                self.save_convertible_bond_data = cb.save_data if cb else lambda x: None
                self.get_bw_data = (lambda year=None: bw.load_data()) if bw else lambda x: []
                self.save_bw_data = bw.save_data if bw else lambda x: None

        disclosure_repo = MultiRepoWrapper(
            capital_increase_repository, bonus_issue_repository, convertible_bond_repository, bw_repository
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
                        if alias:
                            ticker_map[alias] = ticker
            return ticker_map
        except Exception as e:
            logger.error(f"[StatisticsService] 티커 맵 생성 실패: {e}")
            return ticker_map

    def _enrich_tickers(self, items: list) -> list:
        """아이템 리스트의 티커 정보를 보강하고, 매니페스트 상의 실제 할당 상태를 매핑합니다."""
        ticker_map = self._build_local_ticker_map()

        # 로컬 매니페스트 로드
        manifest = {"new_listings": {}}
        if self._manifest_path.exists():
            try:
                manifest = json.loads(self._manifest_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        new_listings_meta = manifest.get("new_listings", {})

        for item in items:
            if hasattr(item, "ticker") and not item.ticker:
                if item.name in ticker_map:
                    item.ticker = ticker_map[item.name]

            # 매니페스트 내 상태 데이터 맵핑
            # Pydantic 모델의 경우 status 필드가 있는 경우에만 상태 정보를 바인딩합니다.
            if hasattr(type(item), "model_fields") and "status" in type(item).model_fields:
                if hasattr(item, "ticker") and item.ticker:
                    meta = new_listings_meta.get(item.ticker, {})
                    item.status = meta.get("status", "PENDING")
                    item.current_board = meta.get("current_board", "virtual_신규상장주")
                    item.current_path = meta.get("current_path", [])
                else:
                    item.status = "PENDING"
                    item.current_board = "virtual_신규상장주"
                    item.current_path = []

        return items

    async def get_daily_ranking(
        self, date_str: str, market: Any = None, subject: Any = None
    ) -> list[DailyMarketRanking] | DailyMarketRanking | None:
        return await self.ranking_svc.get_daily_ranking(date_str, market, subject)

    def save_rankings(self, rankings: list[DailyMarketRanking]):
        """랭킹 데이터 리스트를 저장합니다."""
        for r in rankings:
            self.ranking_svc.repository.save_daily_ranking(r)

    async def get_analyzed_ranking(self, date: str, market: Any, subject: Any) -> DailyMarketRankingAnalysis:
        return await self.ranking_svc.get_analyzed_ranking(date, market, subject)

    async def get_daily_summary(self, date: str) -> dict:
        return await self.ranking_svc.get_daily_summary(date)

    async def get_monthly_ranking(self, month: str, market: Any, subject: Any) -> Any:
        result = await self.ranking_svc.get_monthly_ranking(month, market, subject)
        if result and result.items:
            self._enrich_tickers(result.items)
        return result

    # --- 상한가 분석 (Price Stats) ---
    async def get_ceiling_analysis(self, date: str, force_sync: bool = False) -> CeilingAnalysisReport | None:
        return await self.ceiling_svc.get_ceiling_analysis(date, force_sync=force_sync)

    async def list_available_ceiling_years(self) -> list[str]:
        return await self.ceiling_svc.list_available_years()

    async def list_available_ceiling_dates(self, year: str) -> list[str]:
        return await self.ceiling_svc.list_available_dates(year)

    # --- 공시 분석 (Disclosure) ---
    async def get_capital_increase_data(self, force_sync: bool = False, year: str = "2026") -> list:
        """[DEPRECATED] 유상증자 데이터를 가져옵니다."""
        items = await self.disclosure_svc.get_data("capital_increase", year, force_sync=force_sync)
        return self._enrich_tickers(items)

    async def get_bonus_issue_data(self, force_sync: bool = False, year: str = "2026") -> list:
        items = await self.disclosure_svc.get_data("bonus_issue", year, force_sync=force_sync)
        return self._enrich_tickers(items)

    async def get_convertible_bond_data(self, force_sync: bool = False, year: str = "2026") -> list:
        """[DEPRECATED] 전환사채 데이터를 가져옵니다."""
        items = await self.disclosure_svc.get_data("cb", year, force_sync=force_sync)
        return self._enrich_tickers(items)

    async def get_bw_data(self, force_sync: bool = False, year: str = "2026") -> list:
        """[DEPRECATED] BW 데이터를 가져옵니다."""
        items = await self.disclosure_svc.get_data("bw", year, force_sync=force_sync)
        return self._enrich_tickers(items)

    # --- 신규 상장 (IPO) ---
    async def get_new_listing_data(self, force_sync: bool = False, year: str = "2026") -> list[NewListing]:
        items = await self.ipo_svc.get_data(year, force_sync=force_sync)
        enriched_items = self._enrich_tickers(items)
        self.sync_new_listings_to_virtual_board(enriched_items)
        return enriched_items

    # --- 동기화 명령 (Sync) ---
    async def sync_new_listing_data(self, year: str = "2026") -> list[NewListing]:
        items = await self.ipo_svc.sync_data(year)
        enriched_items = self._enrich_tickers(items)
        self.sync_new_listings_to_virtual_board(enriched_items)
        return enriched_items

    async def sync_all_new_listings(self, force_sync: bool = False) -> list[NewListing]:
        """2024년부터 2026년까지의 모든 신규상장주 데이터를 루프 돌며 일괄 동기화 및 가상보드에 병합 적재합니다."""
        years = ["2024", "2025", "2026"]
        all_enriched_items = []
        
        for year in years:
            try:
                # get_data 내부적으로 force_sync=True 이면 sync_data를 호출하고,
                # sync_data 내부에 추가된 스마트 캐싱 조건에 따라 구글 드라이브 파일과 조건부 다운로드 수행함
                items = await self.ipo_svc.get_data(year, force_sync=force_sync)
                enriched = self._enrich_tickers(items)
                all_enriched_items.extend(enriched)
            except Exception as e:
                logger.error(f"[StatisticsService] {year}년 신규상장 동기화 중 오류 발생: {e}")
                
        # 병합된 전체 연도의 PENDING 항목들을 가상보드 및 매니페스트에 일괄 반영
        self.sync_new_listings_to_virtual_board(all_enriched_items)
        return all_enriched_items

    def sync_new_listings_to_virtual_board(self, listings: list[NewListing]) -> None:
        """신규 상장된 종목들을 매니페스트와 가상보드에 자동으로 적재합니다. (정합성 보장)"""
        if not listings:
            return

        manifest_path = self._manifest_path
        virtual_board_path = self._virtual_board_path

        # 1. 통합 매니페스트 로드
        manifest = {"last_updated": "", "boards": {}, "new_listings": {}}
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.error(
                    f"[StatisticsService] 매니페스트 로드 및 파싱 실패(데이터 보호를 위해 처리를 중단합니다): {e}"
                )
                return

        if "new_listings" not in manifest:
            manifest["new_listings"] = {}

        # 2. 가상보드 로드
        virtual_board = {"name": "신규상장주", "root": {"name": "신규상장주", "depth": 0, "stocks": []}}
        if virtual_board_path.exists():
            try:
                virtual_board = json.loads(virtual_board_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.error(
                    f"[StatisticsService] 가상보드 로드 및 파싱 실패(데이터 보호를 위해 처리를 중단합니다): {e}"
                )
                return

        if "stocks" not in virtual_board["root"]:
            virtual_board["root"]["stocks"] = []

        changed = False
        now_str = datetime.now(UTC).isoformat()

        # 3. 새로운 종목들 중 매니페스트에 없는 항목을 PENDING으로 등록
        for item in listings:
            if not item.ticker or item.ticker == "none":
                continue

            ticker = item.ticker
            # 매니페스트에 아직 등록되지 않은 경우
            if ticker not in manifest["new_listings"]:
                manifest["new_listings"][ticker] = {
                    "ticker": ticker,
                    "name": item.name,
                    "listing_date": item.listing_date or "",
                    "status": "PENDING",
                    "updated_at": now_str,
                    "current_board": "virtual_신규상장주",
                    "current_path": []
                }
                changed = True
            else:
                # 이미 등록된 항목에 listing_date가 없으면 보강
                entry = manifest["new_listings"][ticker]
                if not entry.get("listing_date") and item.listing_date:
                    entry["listing_date"] = item.listing_date
                    changed = True

            # 가상보드 대기 목록에 등록 (PENDING이고 아직 가상보드에 기록되지 않은 경우)
            if manifest["new_listings"][ticker]["status"] == "PENDING":
                exists_in_board = any(s.get("ticker") == ticker for s in virtual_board["root"]["stocks"])
                if not exists_in_board:
                    virtual_board["root"]["stocks"].append({
                        "name": item.name,
                        "ticker": ticker
                    })
                    changed = True

        # 4. 변경사항이 있으면 저장
        if changed:
            try:
                # 매니페스트 저장
                manifest["last_updated"] = now_str
                manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

                # 가상보드 저장
                virtual_board_path.write_text(json.dumps(virtual_board, indent=2, ensure_ascii=False), encoding="utf-8")
                logger.info(f"[StatisticsService] 신규 상장주 {len(listings)}건 가상보드 및 매니페스트 갱신 완료")
            except Exception as e:
                logger.error(f"[StatisticsService] 가상보드 및 매니페스트 갱신 저장 실패: {e}")

    async def sync_capital_increase_data(self, year: str = "2026") -> list:
        items = await self.disclosure_svc.sync_data("capital_increase", year)
        return self._enrich_tickers(items)

    async def sync_recent_data(self, limit: int = 5) -> int:
        """최근 랭킹 데이터를 동기화합니다."""
        # RankingService.sync_data는 단일 날짜 또는 최신 날짜 동기화이므로
        # 여러 날짜를 하려면 별도 루프 필요할 수 있음.
        # 여기서는 단순 위임 또는 최근 N일치 처리 로직 구현.
        # 기존 router는 count를 기대함.
        res = await self.ranking_svc.sync_data()
        return len(res) if res else 0

    def list_available_dates(self, market: Any, subject: Any) -> list[str]:
        return self.ranking_svc.repository.list_available_dates(market, subject)

    @property
    def _repository(self):
        """하위 호환성을 위해 랭킹 레포지토리를 반환합니다."""
        return self.ranking_svc.repository
