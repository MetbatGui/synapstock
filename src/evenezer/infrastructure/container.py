"""Evenezer 전역 의존성 주입(DI) 컨테이너.

애플리케이션의 모든 어댑터와 도메인 서비스의 생명주기를 중앙에서 관리합니다.
웹 서버(FastAPI)와 텔레그램 봇 모두 이 컨테이너를 통해 싱글톤 인스턴스를 공유합니다.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from evenezer.application.services.news_service import NewsService
    from evenezer.domain.ports import FinancialDataPort

from evenezer.application.events.worker import OutboxWorker
from evenezer.application.services.board_file_sync_service import BoardFileSyncService
from evenezer.application.services.command_service import BoardCommandService
from evenezer.application.services.financial_service import FinancialService
from evenezer.application.services.financial_sync_service import FinancialSyncService
from evenezer.application.services.heatmap.heatmap_service import HeatmapService
from evenezer.application.services.media_service import StockMediaService
from evenezer.application.services.query_service import BoardQueryService
from evenezer.application.services.report_service import ReportService
from evenezer.application.services.statistics_service import StatisticsService
from evenezer.application.services.stock_split_sync_service import StockSplitSyncService
from evenezer.application.services.sync_service import BoardSyncService
from evenezer.application.services.weekly_change_service import WeeklyChangeService
from evenezer.domain.events import (
    BatchStocksDeletedFromBoard,
    BoardCreated,
    BoardDeleted,
    NodeAdded,
    NodeDeleted,
    StockAddedToBoard,
    StockDeletedFromBoard,
)
from evenezer.domain.ports import KrxDataPort as DomainKrxDataPort
from evenezer.infrastructure.adapters.disclosure.disclosure_adapter import (
    DartDisclosureAdapter,
)
from evenezer.infrastructure.adapters.events.file_outbox import LocalFileEventOutboxAdapter
from evenezer.infrastructure.adapters.events.in_memory_bus import InMemoryEventBusAdapter
from evenezer.infrastructure.adapters.financial.excel_adapter import (
    ExcelFinancialDataAdapter,
)
from evenezer.infrastructure.adapters.google.google_drive_adapter import GoogleDriveAdapter
from evenezer.infrastructure.adapters.heatmap.caching_krx_repository import CachingKrxRepository
from evenezer.infrastructure.adapters.heatmap.krx_repository import KrxRepository
from evenezer.infrastructure.adapters.krx.native_krx_adapter import NativeKrxAdapter
from evenezer.infrastructure.adapters.local.board_repo import LocalBoardRepository, LocalBoardSyncManifestRepository
from evenezer.infrastructure.adapters.local.file_storage import (
    LocalFileStorageAdapter,
)
from evenezer.infrastructure.adapters.local.statistics_repo import (
    LocalBonusIssueRepository,
    LocalCeilingRepository,
    LocalStatisticsRepository,
    LocalWeeklyChangeRepository,
)
from evenezer.infrastructure.adapters.local.stock_split_repo import LocalStockSplitRepository
from evenezer.infrastructure.adapters.miro.miro_mindmap import MiroMindmapAdapter
from evenezer.infrastructure.adapters.scraper.httpx_scraper import (
    HttpxNewsScraperAdapter,
)
from evenezer.infrastructure.adapters.scraper.naver_ticker_adapter import (
    NaverTickerSearchAdapter,
)
from evenezer.infrastructure.config import AppConfig
from evenezer.infrastructure.persistence.excel_financial_repository import ExcelFinancialRepository


class Container:
    """애플리케이션 전역 의존성을 조립하고 관리하는 컨테이너 클래스."""

    def __init__(self):
        """Container를 초기화하고 전역 애플리케이션 의존성(어댑터, 서비스, 포트)을 조립합니다."""
        # 1. 설정 로드 및 필수 디렉토리 보장
        self.config = AppConfig.load()
        self.config.ensure_directories()

        # 3. 인프라 어댑터 싱글톤
        self._event_bus = InMemoryEventBusAdapter()
        self._outbox = LocalFileEventOutboxAdapter(self.config.outbox_dir)
        self._repo = LocalBoardRepository(self.config.board_dir)
        self._board_sync_manifest_repo = LocalBoardSyncManifestRepository(
            self.config.board_dir / "board_sync_manifest.json"
        )
        self._miro_adapter = MiroMindmapAdapter(self.config.miro_token)

        self._disclosure_adapter = DartDisclosureAdapter()
        self._financial_adapter = ExcelFinancialDataAdapter(self.config.financial_dir / "재무제표.xlsx")
        self._ticker_search_adapter = NaverTickerSearchAdapter(cache_path=str(self.config.stock_cache_path))
        self._news_scraper_adapter = HttpxNewsScraperAdapter()
        self._krx_adapter = CachingKrxRepository(NativeKrxAdapter())

        # 저장소 어댑터 (기존 로컬 파일 시스템 작업 추상화)
        self._report_storage = LocalFileStorageAdapter(self.config.report_dir)
        self._pdf_storage = LocalFileStorageAdapter(self.config.pdf_dir)
        self._statistics_repo = LocalStatisticsRepository(str(self.config.netbuy_dir))
        self._ceiling_repo = LocalCeilingRepository(str(self.config.ceiling_dir))
        self._capital_increase_repo = None  # LocalCapitalIncreaseRepository(str(self.config.capital_increase_dir))
        self._bonus_issue_repo = LocalBonusIssueRepository(str(self.config.bonus_issue_dir))
        self._convertible_bond_repo = None  # LocalConvertibleBondRepository(str(self.config.convertible_bond_dir))
        self._bw_repo = None  # LocalBondWithWarrantsRepository(str(self.config.bw_dir))
        self._weekly_change_repo = LocalWeeklyChangeRepository(str(self.config.weekly_change_dir))
        self._stock_split_repo = LocalStockSplitRepository(str(self.config.stock_split_dir))

        from evenezer.infrastructure.adapters.local.news_repo import LocalNewsRepository

        self._news_repo = LocalNewsRepository(self.config.news_dir)
        self._financial_repo = ExcelFinancialRepository(
            str(self.config.data_dir / "financial_statements" / "재무제표.xlsx")
        )

        # 4. 조건부 어댑터 (Google Drive)
        self._drive_adapter = None
        self._init_google_drive()

        # 5. 도메인 서비스 싱글톤
        self._board_file_sync_service = BoardFileSyncService(
            repository=self._repo,
            drive_adapter=self._drive_adapter,
            theme_folder_id=self.config.theme_folder_id,
            manifest_repository=self._board_sync_manifest_repo,
        )

        self._query_service = BoardQueryService(
            repository=self._repo,
            ticker_search=self._ticker_search_adapter,
            disclosure=self._disclosure_adapter,
            financial=cast("FinancialDataPort", self._financial_adapter),
        )
        self._command_service = BoardCommandService(repository=self._repo, event_bus=self._event_bus)

        # 도메인 이벤트 핸들러 바인딩 (동기 매니페스트 업데이트 즉시 실행)
        self._event_bus.subscribe(
            BoardCreated, lambda ev: self._board_file_sync_service.update_local_manifest(ev.board_id, deleted=False)
        )
        self._event_bus.subscribe(
            BoardDeleted, lambda ev: self._board_file_sync_service.update_local_manifest(ev.board_id, deleted=True)
        )
        self._event_bus.subscribe(
            NodeAdded, lambda ev: self._board_file_sync_service.update_local_manifest(ev.board_id, deleted=False)
        )
        self._event_bus.subscribe(
            NodeDeleted, lambda ev: self._board_file_sync_service.update_local_manifest(ev.board_id, deleted=False)
        )

        # 무거운 비동기 동기화 이벤트는 아웃박스에 PENDING 상태로 적재
        self._event_bus.subscribe(StockAddedToBoard, lambda ev: self._outbox.save(ev))
        self._event_bus.subscribe(StockDeletedFromBoard, lambda ev: self._outbox.save(ev))
        self._event_bus.subscribe(BatchStocksDeletedFromBoard, lambda ev: self._outbox.save(ev))

        # OutboxWorker 전선 조립 (BoardFileSyncService의 핸들러 메소드들을 직접 바인딩)
        board_handlers = {
            "StockAddedToBoard": self._board_file_sync_service.handle_stock_added_event,
            "StockDeletedFromBoard": self._board_file_sync_service.handle_stock_deleted_event,
            "BatchStocksDeletedFromBoard": self._board_file_sync_service.handle_batch_stocks_deleted_event,
        }
        self._outbox_worker = OutboxWorker(outbox=self._outbox, handlers=board_handlers)

        from evenezer.application.services.news_service import NewsService

        self._news_service = NewsService(
            repository=self._news_repo,
            scraper=self._news_scraper_adapter,
            drive_adapter=self._drive_adapter,
            news_folder_id=self.config.news_folder_id,
        )

        self._media_service = StockMediaService(
            repository=self._repo,
            storage=self._pdf_storage,
            news_service=self._news_service,
            pdf_dir=str(self.config.pdf_dir),
        )
        self._sync_service = BoardSyncService(mindmap=self._miro_adapter, ticker_search=self._ticker_search_adapter)

        self._statistics_service = StatisticsService(
            storage=self._drive_adapter,
            repository=self._statistics_repo,
            query_service=self._query_service,
            ceiling_repository=self._ceiling_repo,
            capital_increase_repository=self._capital_increase_repo,
            bonus_issue_repository=self._bonus_issue_repo,
            convertible_bond_repository=self._convertible_bond_repo,
            bw_repository=self._bw_repo,
            manifest_repository=self._board_sync_manifest_repo,
            board_file_sync_service=self._board_file_sync_service,
            board_repository=self._repo,
            krx_repo=self._krx_adapter,
        )

        self._financial_service = FinancialService(repository=self._financial_repo)
        self._financial_sync_service = FinancialSyncService(
            drive_adapter=self._drive_adapter,
            financial_statements_id=self.config.financial_statements_id,
            financial_dir=self.config.financial_dir,
            financial_repo=self._financial_repo,
        )
        self._weekly_change_service = WeeklyChangeService(
            drive_adapter=self._drive_adapter,
            folder_id=self.config.weekly_change_folder_id,
            repository=self._weekly_change_repo,
        )
        self._stock_split_sync_service = StockSplitSyncService(
            repository=self._stock_split_repo,
            drive_adapter=self._drive_adapter,
            stock_split_folder_id=self.config.stock_split_folder_id,
        )

        from evenezer.infrastructure.adapters.heatmap.file_repository import JsonThemeDataLoader

        self._heatmap_loader = JsonThemeDataLoader(
            json_dir=str(self.config.heatmap_dir),
            drive_adapter=self._drive_adapter,
            folder_id=self.config.heatmap_folder_id,
        )
        self._heatmap_krx_repository = CachingKrxRepository(KrxRepository())
        self._heatmap_service = HeatmapService(
            loader=self._heatmap_loader,
            krx_repo=self._heatmap_krx_repository,
        )

        self._report_service = None
        self._init_report_service()

    def start_background_services(self) -> None:
        """재무제표, 테마 보드, 주식 분할, 히트맵 등의 백그라운드 동기화 스레드 및 아웃박스 워커를 기동합니다."""
        logger.info("[Container] 백그라운드 서비스 기동 시작...")
        self.sync_financial_statements_from_drive()
        self.sync_boards_from_drive_in_background()
        self.sync_stock_splits_from_drive_in_background()
        self.sync_heatmap_from_drive_in_background()
        self._outbox_worker.start()
        logger.info("[Container] 모든 백그라운드 서비스 기동 완료.")

    async def close_services(self) -> None:
        """백그라운드 아웃박스 워커와 네트워크 스크래퍼 세션 등의 리소스를 안전하게 종료하고 해제합니다."""
        logger.info("[Container] 서비스 종료 및 리소스 해제 중...")
        self._outbox_worker.stop()
        if hasattr(self, "_news_scraper_adapter") and self._news_scraper_adapter:
            await self._news_scraper_adapter.close()
        logger.info("[Container] 서비스 종료 완료.")

    def _init_google_drive(self):
        """환경 변수 및 로컬 secrets 디렉토리의 자격 증명 파일(token.json, client_secret.json) 정보를 확인하고
        구글 드라이브 어댑터 인스턴스를 조립합니다.
        """
        token_path = self.config.secrets_dir / "token.json"
        client_secret_path = self.config.secrets_dir / "client_secret.json"

        if not token_path.exists():
            logger.warning("[Container] Google Drive token.json 파일이 없어 어댑터를 초기화하지 않습니다.")
            return

        try:
            folders = {
                "report": self.config.report_folder_id,
                "sd": self.config.sd_folder_id,
                "ceiling": self.config.ceiling_folder_id,
                # "capital_increase": self.config.capital_increase_folder_id,
                "bonus_issue": self.config.bonus_issue_folder_id,
                # "convertible_bond": self.config.convertible_bond_folder_id,
                # "bw": self.config.bw_folder_id,
                "new_listing": self.config.new_listing_folder_id,
                "news": self.config.news_folder_id,
                "weekly_change": self.config.weekly_change_folder_id,
                "stock_split": self.config.stock_split_folder_id,
                "heatmap": self.config.heatmap_folder_id,
            }

            # None이 아닌 폴더 ID만 포함하여 dict[str, str] 보장
            valid_folders = {k: v for k, v in folders.items() if v is not None}

            self._drive_adapter = GoogleDriveAdapter(
                token_file=str(token_path),
                folders=valid_folders,
                client_secret_file=str(client_secret_path),
            )
        except Exception as e:
            logger.error(f"[Container] Google Drive 어댑터 초기화 실패: {e}")

    def _init_report_service(self):
        """Google Drive 어댑터 및 리포트 폴더 ID가 유효한 경우, 파일 동기화 기반의 ReportService를 초기화합니다."""
        if self._drive_adapter and self.config.report_folder_id:
            self._report_service = ReportService(
                cloud_storage=self._drive_adapter,
                local_storage=self._report_storage,
                report_folder_id=self.config.report_folder_id,
                report_dir=str(self.config.report_dir),
            )

    def _run_in_background_thread(self, coro_func, thread_name: str):
        """비동기 코루틴 함수를 백그라운드 데몬 스레드에서 기동하는 헬퍼"""
        import threading
        import asyncio

        def run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(coro_func())
            except Exception as e:
                logger.error(f"[Container] 백그라운드 {thread_name} 중 예외 발생: {e}")
            finally:
                loop.close()

        t = threading.Thread(target=run, name=thread_name, daemon=True)
        t.start()
        logger.info(f"[Container] 백그라운드 {thread_name} 스레드를 성공적으로 시작했습니다.")

    def sync_financial_statements_from_drive(self):
        """Google Drive에 업로드된 최신 재무제표 엑셀 파일을 로컬에 동기화하기 위한 백그라운드 데몬 스레드를 실행합니다."""
        self._run_in_background_thread(self._financial_sync_service.sync, "FinancialSyncThread")

    def sync_boards_from_drive_in_background(self):
        """로컬 가상/테마 보드 데이터와 Google Drive 내 파일을 양방향 동기화하는 백그라운드 데몬 스레드를 실행합니다."""
        if not self._drive_adapter or not self.config.theme_folder_id:
            logger.info(
                "[Container] 가상/테마 보드 구글 드라이브 폴더 ID가 없거나 어댑터가 활성화되지 않아 동기화를 건너뜁니다."
            )
            return

        self._run_in_background_thread(self._board_file_sync_service.sync_with_drive, "BoardSyncThread")

    def sync_stock_splits_from_drive_in_background(self):
        """Google Drive로부터 액면분할/합병 데이터를 주기적으로 조회해 로컬 저장소에 반영하는 백그라운드 동기화 스레드를 기동합니다."""
        if not self._drive_adapter or not self.config.stock_split_folder_id:
            logger.info(
                "[Container] 주식 분할 구글 드라이브 폴더 ID가 없거나 어댑터가 활성화되지 않아 동기화를 건너뜁니다."
            )
            return

        self._run_in_background_thread(self._stock_split_sync_service.sync, "StockSplitSyncThread")

    def sync_heatmap_from_drive_in_background(self):
        """Google Drive에 업로드된 히트맵용 테마 JSON 파일군을 로컬 캐시 폴더와 동기화하는 백그라운드 스레드를 기동합니다."""
        if not self._drive_adapter:
            logger.info("[Container] 어댑터가 활성화되지 않아 히트맵 동기화를 건너뜁니다.")
            return

        self._run_in_background_thread(self._heatmap_service.sync_from_drive, "HeatmapSyncThread")



    # ── Property 접근자 (Read-only) ──────────────────────────────────────────

    @property
    def event_bus(self) -> InMemoryEventBusAdapter:
        return self._event_bus

    @property
    def query_service(self) -> BoardQueryService:
        return self._query_service

    @property
    def command_service(self) -> BoardCommandService:
        return self._command_service

    @property
    def media_service(self) -> StockMediaService:
        return self._media_service

    @property
    def sync_service(self) -> BoardSyncService:
        return self._sync_service

    @property
    def report_service(self) -> ReportService | None:
        return self._report_service

    @property
    def ceiling_repo(self) -> LocalCeilingRepository:
        return self._ceiling_repo

    @property
    def drive_adapter(self) -> GoogleDriveAdapter | None:
        return self._drive_adapter

    @property
    def news_scraper(self) -> HttpxNewsScraperAdapter:
        return self._news_scraper_adapter

    @property
    def statistics_service(self) -> StatisticsService:
        return self._statistics_service

    @property
    def krx_adapter(self) -> DomainKrxDataPort:
        return self._krx_adapter

    @property
    def heatmap_service(self) -> HeatmapService:
        return self._heatmap_service

    @property
    def news_service(self) -> NewsService:
        return self._news_service

    @property
    def financial_service(self) -> FinancialService:
        return self._financial_service

    @property
    def financial_sync_service(self) -> FinancialSyncService:
        return self._financial_sync_service

    @property
    def weekly_change_service(self) -> WeeklyChangeService:
        return self._weekly_change_service

    @property
    def board_file_sync_service(self) -> BoardFileSyncService:
        return self._board_file_sync_service

    @property
    def outbox_worker(self) -> OutboxWorker:
        return self._outbox_worker


# 전역 컨테이너 인스턴스 생성
container = Container()
