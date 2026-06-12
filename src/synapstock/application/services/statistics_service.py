import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from synapstock.application.services.ceiling_analysis_service import CeilingAnalysisService
from synapstock.application.services.disclosure_analysis_service import DisclosureAnalysisService
from synapstock.application.services.new_listing_service import NewListingService
from synapstock.application.services.ranking_service import RankingService
from synapstock.domain.statistics.domain_service import NewListingSyncDomainService
from synapstock.domain.statistics.models import (
    CeilingAnalysisReport,
    DailyMarketRanking,
    DailyMarketRankingAnalysis,
    NewListing,
)
from synapstock.domain.ports import BoardSyncManifestRepositoryPort


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
        manifest_repository: BoardSyncManifestRepositoryPort | None = None,
        board_file_sync_service: Any = None,
        board_repository: Any = None,
    ):
        self._storage = storage
        self._query_service = query_service
        self._manifest_repository = manifest_repository
        self._board_file_sync_service = board_file_sync_service
        self._board_repository = board_repository


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

    def _enrich_tickers(self, items: list, skip_search: bool = False) -> list:
        """아이템 리스트의 티커 정보를 보강하고, 매니페스트 상의 실제 할당 상태를 매핑합니다."""
        ticker_map = self._build_local_ticker_map()

        # 로컬 매니페스트 로드
        manifest = None
        if self._manifest_repository:
            manifest = self._manifest_repository.load()
        new_listings_meta = manifest.new_listings if manifest else {}

        for item in items:
            if hasattr(item, "ticker") and not item.ticker:
                if item.name in ticker_map:
                    item.ticker = ticker_map[item.name]
                elif self._query_service and not skip_search:
                    # 로컬 보드에 등록되지 않은 신규 종목은 네이버 API를 통해 티커 검색을 수행
                    try:
                        search_results = self._query_service.search_ticker(item.name)
                        found = False
                        if search_results:
                            import unicodedata
                            clean_item_name = unicodedata.normalize("NFC", item.name).strip().lower()
                            for res in search_results:
                                res_name = unicodedata.normalize("NFC", res.get("name", "")).strip().lower()
                                if res_name == clean_item_name or clean_item_name in res_name:
                                    ticker = res.get("ticker")
                                    if ticker and ticker.isalnum() and len(ticker) == 6:
                                        item.ticker = ticker
                                        logger.info(f"[StatisticsService] 신규 종목 티커 검색 성공: {item.name} -> {ticker}")
                                        found = True
                                        break
                        if not found:
                            item.ticker = "none"
                    except Exception as e:
                        logger.error(f"[StatisticsService] 신규 종목({item.name}) 티커 검색 실패: {e}")

            # 매니페스트 내 상태 데이터 맵핑
            # Pydantic 모델의 경우 status 필드가 있는 경우에만 상태 정보를 바인딩합니다.
            if hasattr(type(item), "model_fields") and "status" in type(item).model_fields:
                if hasattr(item, "ticker") and item.ticker:
                    meta = new_listings_meta.get(item.ticker)
                    if meta:
                        item.status = meta.status
                        item.current_board = meta.current_board
                        item.current_path = meta.current_path
                    else:
                        item.status = "PENDING"
                        item.current_board = "virtual_신규상장주"
                        item.current_path = []
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
            self._enrich_tickers(result.items, skip_search=True)
            for item in result.items:
                if item.ticker == "none":
                    item.ticker = None
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
        if year == "all":
            years = ["2020", "2021", "2022", "2023", "2024", "2025", "2026"]
            all_items = []
            for y in years:
                try:
                    items = await self.ipo_svc.get_data(y, force_sync=force_sync)
                    enriched = self._enrich_tickers(items)
                    try:
                        self.ipo_svc.repository.save_new_listings(enriched, year=y)
                    except Exception as ex:
                        logger.warning(f"[StatisticsService] 보강된 티커 캐시 저장 실패 ({y}): {ex}")
                    all_items.extend(enriched)
                except Exception as e:
                    logger.error(f"[StatisticsService] {y}년 신규상장 데이터 로드 실패: {e}")
            changed = self.sync_new_listings_to_virtual_board(all_items)
            if changed and self._board_file_sync_service:
                await self._board_file_sync_service.sync_with_drive()
            return all_items
        else:
            items = await self.ipo_svc.get_data(year, force_sync=force_sync)
            enriched_items = self._enrich_tickers(items)
            try:
                self.ipo_svc.repository.save_new_listings(enriched_items, year=year)
            except Exception as ex:
                logger.warning(f"[StatisticsService] 보강된 티커 캐시 저장 실패 ({year}): {ex}")
            changed = self.sync_new_listings_to_virtual_board(enriched_items)
            if changed and self._board_file_sync_service:
                await self._board_file_sync_service.sync_with_drive()
            return enriched_items

    # --- 동기화 명령 (Sync) ---
    async def sync_new_listing_data(self, year: str = "2026") -> list[NewListing]:
        items = await self.ipo_svc.sync_data(year)
        enriched_items = self._enrich_tickers(items)
        try:
            self.ipo_svc.repository.save_new_listings(enriched_items, year=year)
        except Exception as ex:
            logger.warning(f"[StatisticsService] 보강된 티커 캐시 저장 실패 ({year}): {ex}")
        changed = self.sync_new_listings_to_virtual_board(enriched_items)
        if changed and self._board_file_sync_service:
            await self._board_file_sync_service.sync_with_drive()
        return enriched_items

    async def sync_all_new_listings(self, force_sync: bool = False) -> list[NewListing]:
        """2020년부터 2026년까지의 모든 신규상장주 데이터를 루프 돌며 일괄 동기화 및 가상보드에 병합 적재합니다."""
        years = ["2020", "2021", "2022", "2023", "2024", "2025", "2026"]
        all_enriched_items = []
        
        for year in years:
            try:
                # get_data 내부적으로 force_sync=True 이면 sync_data를 호출하고,
                # sync_data 내부에 추가된 스마트 캐싱 조건에 따라 구글 드라이브 파일과 조건부 다운로드 수행함
                items = await self.ipo_svc.get_data(year, force_sync=force_sync)
                enriched = self._enrich_tickers(items)
                try:
                    self.ipo_svc.repository.save_new_listings(enriched, year=year)
                except Exception as ex:
                    logger.warning(f"[StatisticsService] 보강된 티커 캐시 저장 실패 ({year}): {ex}")
                all_enriched_items.extend(enriched)
            except Exception as e:
                logger.error(f"[StatisticsService] {year}년 신규상장 동기화 중 오류 발생: {e}")
                
        # 병합된 전체 연도의 PENDING 항목들을 가상보드 및 매니페스트에 일괄 반영
        changed = self.sync_new_listings_to_virtual_board(all_enriched_items)
        if changed and self._board_file_sync_service:
            await self._board_file_sync_service.sync_with_drive()
        return all_enriched_items

    def sync_new_listings_to_virtual_board(self, listings: list[NewListing]) -> bool:
        """신규 상장된 종목들을 매니페스트와 가상보드에 자동으로 적재합니다. (도메인 서비스 위임)"""
        if not listings:
            return False

        if not self._manifest_repository:
            logger.error("[StatisticsService] 매니페스트 리포지토리가 설정되지 않아 처리를 중단합니다.")
            return False

        # 1. 통합 매니페스트 로드
        manifest = self._manifest_repository.load()

        # 2. 가상보드 로드 (BoardRepositoryPort 사용)
        # 로드 실패 시 새 Board 인스턴스 자동 생성
        virtual_board = None
        if self._board_repository:
            try:
                virtual_board = self._board_repository.load("virtual_신규상장주")
            except FileNotFoundError:
                pass
            except Exception as e:
                logger.error(f"[StatisticsService] 가상보드 로드 실패: {e}")

        if not virtual_board:
            from synapstock.domain.models import Board, Node
            root_node = Node(name="신규상장주", depth=0)
            virtual_board = Board(id="virtual_신규상장주", name="신규상장주", root=root_node)

        # 3. 마인드맵의 일반 테마 보드들에 기등록된 종목 맵 캐싱
        assigned_stocks_map = {}
        if self._query_service:
            try:
                flat_stocks = self._query_service.get_all_stocks_flat()
                for s in flat_stocks:
                    t = s.get("ticker")
                    b = s.get("board")
                    p = s.get("path", [])
                    if t and b and b != "virtual_신규상장주":
                        assigned_stocks_map[t] = (b, p)
            except Exception as e:
                logger.error(f"[StatisticsService] 마인드맵 등록 종목 캐시 맵 구성 실패: {e}")

        # 4. 도메인 서비스를 통한 비즈니스 로직 수행
        now_str = datetime.now(UTC).isoformat()
        listings_meta_dict = {
            ticker: model.model_dump() for ticker, model in manifest.new_listings.items()
        }
        virtual_board, updated_listings_dict, changed = NewListingSyncDomainService.sync_listings_to_virtual_board(
            virtual_board=virtual_board,
            new_listings_meta=listings_meta_dict,
            listings=listings,
            assigned_stocks_map=assigned_stocks_map,
            now_str=now_str
        )

        # 5. 변경사항이 있으면 저장
        if changed:
            try:
                # 5.1. 매니페스트 저장
                manifest.new_listings = {
                    ticker: NewListing.model_validate(raw) for ticker, raw in updated_listings_dict.items()
                }
                manifest.last_updated = now_str
                self._manifest_repository.save(manifest)

                # 5.2. 가상보드 저장 (BoardRepositoryPort 사용)
                if self._board_repository:
                    self._board_repository.save(virtual_board)
                else:
                    logger.warning("[StatisticsService] 가상보드 저장 실패: board_repository가 주입되지 않았습니다.")

                logger.info(f"[StatisticsService] 신규 상장주 {len(listings)}건 가상보드 및 매니페스트 갱신 완료")

                # 5.3. 가상보드 갱신 최종 시각을 매니페스트에 영속화
                if self._board_file_sync_service:
                    self._board_file_sync_service.update_local_manifest("virtual_신규상장주", deleted=False)
                return True
            except Exception as e:
                logger.error(f"[StatisticsService] 가상보드 및 매니페스트 갱신 저장 실패: {e}")
                return False
        return False


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
