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
        # 1. 설정 로드 (환경 변수 및 기본 경로)
        self.config = AppConfig.load()

        # 2. 로컬 디렉토리 보장 (필수 경로들 자동 생성)
        self.config.data_dir.mkdir(parents=True, exist_ok=True)
        self.config.secrets_dir.mkdir(parents=True, exist_ok=True)
        self.config.statistics_dir.mkdir(parents=True, exist_ok=True)
        self.config.netbuy_dir.mkdir(parents=True, exist_ok=True)
        self.config.ceiling_dir.mkdir(parents=True, exist_ok=True)
        # self.config.capital_increase_dir.mkdir(parents=True, exist_ok=True)
        self.config.bonus_issue_dir.mkdir(parents=True, exist_ok=True)
        # self.config.convertible_bond_dir.mkdir(parents=True, exist_ok=True)
        # self.config.bw_dir.mkdir(parents=True, exist_ok=True)
        self.config.new_listing_dir.mkdir(parents=True, exist_ok=True)
        self.config.weekly_change_dir.mkdir(parents=True, exist_ok=True)
        self.config.stock_split_dir.mkdir(parents=True, exist_ok=True)
        self.config.news_dir.mkdir(parents=True, exist_ok=True)
        self.config.heatmap_dir.mkdir(parents=True, exist_ok=True)
        self.config.outbox_dir.mkdir(parents=True, exist_ok=True)

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

        # OutboxWorker 전선 조립
        async def handle_stock_added(ev: StockAddedToBoard):
            manifest = self._board_file_sync_service.load_local_manifest()
            if manifest.is_event_processed(ev.event_id):
                logger.info(f"[Container] 이미 처리된 StockAddedToBoard 이벤트이므로 스킵합니다: {ev.event_id}")
                return

            self._board_file_sync_service.update_local_manifest(ev.board_id, deleted=False)
            await self._board_file_sync_service.handle_stock_addition_trigger(
                ev.ticker, ev.board_id, ev.parent_path.split("/")
            )
            await self._board_file_sync_service.sync_with_drive()

            # 처리 완료 상태 기록
            manifest = self._board_file_sync_service.load_local_manifest()
            manifest.mark_event_processed(ev.event_id)
            self._board_file_sync_service.save_local_manifest(manifest)

        async def handle_stock_deleted(ev: StockDeletedFromBoard):
            manifest = self._board_file_sync_service.load_local_manifest()
            if manifest.is_event_processed(ev.event_id):
                logger.info(f"[Container] 이미 처리된 StockDeletedFromBoard 이벤트이므로 스킵합니다: {ev.event_id}")
                return

            self._board_file_sync_service.update_local_manifest(ev.board_id, deleted=False)
            await self._board_file_sync_service.handle_stock_deletion_trigger(ev.ticker, ev.board_id)
            await self._board_file_sync_service.sync_with_drive()

            # 처리 완료 상태 기록
            manifest = self._board_file_sync_service.load_local_manifest()
            manifest.mark_event_processed(ev.event_id)
            self._board_file_sync_service.save_local_manifest(manifest)

        async def handle_batch_stocks_deleted(ev: BatchStocksDeletedFromBoard):
            manifest = self._board_file_sync_service.load_local_manifest()
            if manifest.is_event_processed(ev.event_id):
                logger.info(
                    f"[Container] 이미 처리된 BatchStocksDeletedFromBoard 이벤트이므로 스킵합니다: {ev.event_id}"
                )
                return

            self._board_file_sync_service.update_local_manifest(ev.board_id, deleted=False)
            await self._board_file_sync_service.handle_batch_stock_deletion_trigger(ev.tickers, ev.board_id)
            await self._board_file_sync_service.sync_with_drive()

            # 처리 완료 상태 기록
            manifest = self._board_file_sync_service.load_local_manifest()
            manifest.mark_event_processed(ev.event_id)
            self._board_file_sync_service.save_local_manifest(manifest)

        board_handlers = {
            "StockAddedToBoard": handle_stock_added,
            "StockDeletedFromBoard": handle_stock_deleted,
            "BatchStocksDeletedFromBoard": handle_batch_stocks_deleted,
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
        if not self._drive_adapter or not self.config.financial_statements_id:
            logger.info("[Container] 재무제표 구글 드라이브 ID가 없거나 어댑터가 활성화되지 않아 동기화를 건너뜁니다.")
            return

        self._run_in_background_thread(self._sync_financial_statements_async, "FinancialSyncThread")

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

    async def _sync_financial_statements_async(self):
        """Google Drive에 있는 최신 재무제표 파일을 비동기적으로 다운로드하고 로컬 파일 변경 시점을 업데이트합니다."""
        import os
        from datetime import datetime

        if not self._drive_adapter:
            logger.warning("[Container] 구글 드라이브 어댑터가 활성화되지 않아 동기화를 중단합니다.")
            return

        adapter = self._drive_adapter
        file_id = self.config.financial_statements_id
        if not file_id:
            logger.warning("[Container] 재무제표 구글 드라이브 ID가 설정되지 않아 동기화를 중단합니다.")
            return

        local_path = self.config.financial_dir / "재무제표.xlsx"

        logger.info(f"[Container] 재무제표 구글 드라이브 동기화 검사 시작 (ID: {file_id})")

        # 1. 구글 드라이브 ID 메타데이터 조회
        meta = await adapter.get_file_metadata(file_id)
        if not meta:
            logger.error("[Container] 구글 드라이브에서 재무제표 메타데이터를 가져오지 못했습니다.")
            return

        mime_type = meta.get("mimeType", "")
        target_file_id = file_id
        target_modified_time_str = meta.get("modifiedTime")
        target_mime_type = mime_type

        # 2. 만약 폴더 ID인 경우, 폴더 내부에서 '재무제표' 이름을 포함한 최신 엑셀/스프레드시트 파일을 검색
        if mime_type == "application/vnd.google-apps.folder":
            logger.info("[Container] 제공된 ID가 폴더이므로 폴더 내부를 검색합니다.")

            def _find_file_in_folder():
                try:
                    query = (
                        f"'{file_id}' in parents and trashed = false and "
                        f"(mimeType = 'application/vnd.google-apps.spreadsheet' or "
                        f"mimeType = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')"
                    )
                    results = (
                        adapter.service.files()
                        .list(q=query, fields="files(id, name, modifiedTime, mimeType)", orderBy="modifiedTime desc")
                        .execute()
                    )
                    return results.get("files", [])
                except Exception as e:
                    logger.error(f"[Container] 폴더 내 파일 검색 실패: {e}")
                    return []

            import asyncio

            files = await asyncio.to_thread(_find_file_in_folder)
            if not files:
                logger.error("[Container] 폴더 내에서 재무제표 엑셀 또는 스프레드시트 파일을 찾지 못했습니다.")
                return

            # 이름에 '재무제표'가 포함된 파일 우선 탐색
            selected_file = next(
                (f for f in files if "재무제표" in f.get("name", "")),
                files[0]
            )

            target_file_id = selected_file["id"]
            target_modified_time_str = selected_file.get("modifiedTime")
            target_mime_type = selected_file.get("mimeType")
            logger.info(
                f"[Container] 동기화 대상 파일 발견: {selected_file.get('name')} (ID: {target_file_id}, MimeType: {target_mime_type})"
            )

        if not target_modified_time_str:
            logger.error("[Container] 대상 파일의 modifiedTime 정보가 없습니다.")
            return

        # Drive 시간 파싱 (UTC -> datetime -> timestamp)
        drive_dt = datetime.fromisoformat(target_modified_time_str.replace("Z", "+00:00"))
        drive_mtime = drive_dt.timestamp()

        # 3. 로컬 파일 시간 조회
        local_mtime = 0.0
        if local_path.exists():
            local_mtime = os.path.getmtime(local_path)

        # 4. 변경 날짜 대조 후 가져오기
        if not local_path.exists() or (drive_mtime - local_mtime) > 1.0:
            logger.info(
                f"[Container] 구글 드라이브 재무제표 파일이 더 최신입니다. 다운로드를 시작합니다. "
                f"(Drive: {drive_dt}, Local Mtime: {datetime.fromtimestamp(local_mtime) if local_mtime else '없음'})"
            )

            # 다운로드 실행
            data = await adapter.get_file_by_id(target_file_id)
            if data:
                # 폴더가 없으면 생성
                local_path.parent.mkdir(parents=True, exist_ok=True)
                with open(local_path, "wb") as f:
                    f.write(data)

                # 로컬 파일 수정 시간을 드라이브와 완벽하게 일치시킴
                os.utime(local_path, (drive_mtime, drive_mtime))
                logger.info("[Container] 재무제표 파일 다운로드 및 시간 동기화 성공!")
            else:
                logger.error("[Container] 구글 드라이브에서 재무제표 파일 다운로드 실패")
        else:
            logger.info("[Container] 로컬 재무제표 파일이 최신 상태입니다. 동기화를 건너뜁니다.")

        # 5. 재무제표 데이터를 메모리에 사전 적재 (Eager 로드 웜업)
        if local_path.exists() and self._financial_repo:
            try:
                from evenezer.domain.financials.models import FinancialMetric
                logger.info("[Container] 재무제표 데이터를 메모리에 사전 적재(Warm-up)합니다...")
                self._financial_repo.load_all(FinancialMetric.REVENUE)
                self._financial_repo.load_all(FinancialMetric.OPERATING_PROFIT)
                self._financial_repo.load_all(FinancialMetric.NET_INCOME)
                logger.info("[Container] 재무제표 데이터 사전 적재 완료!")
            except Exception as e:
                logger.error(f"[Container] 재무제표 데이터 사전 적재 중 오류 발생: {e}")

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
