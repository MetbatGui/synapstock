"""SynapStock 전역 의존성 주입(DI) 컨테이너.

애플리케이션의 모든 어댑터와 도메인 서비스의 생명주기를 중앙에서 관리합니다.
웹 서버(FastAPI)와 텔레그램 봇 모두 이 컨테이너를 통해 싱글톤 인스턴스를 공유합니다.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from synapstock.application.services.news_service import NewsService
    from synapstock.domain.ports import FinancialDataPort

from synapstock.application.services.board_file_sync_service import BoardFileSyncService
from synapstock.application.services.command_service import BoardCommandService
from synapstock.application.services.financial_service import FinancialService
from synapstock.application.services.media_service import StockMediaService
from synapstock.application.services.query_service import BoardQueryService
from synapstock.application.services.report_service import ReportService
from synapstock.application.services.statistics_service import StatisticsService
from synapstock.application.services.sync_service import BoardSyncService
from synapstock.application.services.weekly_change_service import WeeklyChangeService
from synapstock.application.services.stock_split_sync_service import StockSplitSyncService
from synapstock.infrastructure.adapters.disclosure.disclosure_adapter import (

    DartDisclosureAdapter,
)
from synapstock.infrastructure.adapters.financial.excel_adapter import (
    ExcelFinancialDataAdapter,
)
from synapstock.infrastructure.adapters.google.google_drive_adapter import (
    GoogleDriveAdapter,
)
from synapstock.infrastructure.adapters.krx.native_krx_adapter import NativeKrxAdapter
from synapstock.infrastructure.adapters.local.board_repo import LocalBoardRepository
from synapstock.infrastructure.adapters.local.file_storage import (
    LocalFileStorageAdapter,
)
from synapstock.infrastructure.adapters.local.statistics_repo import (
    LocalBonusIssueRepository,
    LocalCeilingRepository,
    LocalStatisticsRepository,
    LocalWeeklyChangeRepository,
)
from synapstock.infrastructure.adapters.local.stock_split_repo import LocalStockSplitRepository
from synapstock.infrastructure.adapters.miro.miro_mindmap import MiroMindmapAdapter

from synapstock.infrastructure.adapters.scraper.httpx_scraper import (
    HttpxNewsScraperAdapter,
)
from synapstock.infrastructure.adapters.scraper.naver_ticker_adapter import (
    NaverTickerSearchAdapter,
)
from synapstock.infrastructure.config import AppConfig
from synapstock.infrastructure.persistence.excel_financial_repository import ExcelFinancialRepository

logger = logging.getLogger(__name__)


class Container:
    """애플리케이션 전역 의존성을 조립하고 관리하는 컨테이너 클래스."""

    def __init__(self):
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


        # 3. 인프라 어댑터 싱글톤
        self._repo = LocalBoardRepository(self.config.board_dir)
        self._miro_adapter = MiroMindmapAdapter(self.config.miro_token)
        self._disclosure_adapter = DartDisclosureAdapter()
        self._financial_adapter = ExcelFinancialDataAdapter(self.config.financial_dir / "재무제표.xlsx")
        self._ticker_search_adapter = NaverTickerSearchAdapter(cache_path=str(self.config.stock_cache_path))
        self._news_scraper_adapter = HttpxNewsScraperAdapter()
        self._krx_adapter = NativeKrxAdapter()

        # 저장소 어댑터 (기존 로컬 파일 시스템 작업 추상화)
        self._report_storage = LocalFileStorageAdapter(self.config.report_dir)
        self._pdf_storage = LocalFileStorageAdapter(self.config.pdf_dir)
        self._statistics_repo = LocalStatisticsRepository(str(self.config.netbuy_dir))
        self._ceiling_repo = LocalCeilingRepository(str(self.config.ceiling_dir))
        self._capital_increase_repo = None # LocalCapitalIncreaseRepository(str(self.config.capital_increase_dir))
        self._bonus_issue_repo = LocalBonusIssueRepository(str(self.config.bonus_issue_dir))
        self._convertible_bond_repo = None # LocalConvertibleBondRepository(str(self.config.convertible_bond_dir))
        self._bw_repo = None # LocalBondWithWarrantsRepository(str(self.config.bw_dir))
        self._weekly_change_repo = LocalWeeklyChangeRepository(str(self.config.weekly_change_dir))
        self._stock_split_repo = LocalStockSplitRepository(str(self.config.stock_split_dir))


        from synapstock.infrastructure.adapters.local.news_repo import LocalNewsRepository

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
            manifest_path=self.config.board_dir / "board_sync_manifest.json"
        )
        self._query_service = BoardQueryService(
            repository=self._repo,
            ticker_search=self._ticker_search_adapter,
            disclosure=self._disclosure_adapter,
            financial=cast("FinancialDataPort", self._financial_adapter),
        )
        self._command_service = BoardCommandService(
            repository=self._repo,
            sync_service=self._board_file_sync_service
        )

        from synapstock.application.services.news_service import NewsService

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
            manifest_path=self.config.board_dir / "board_sync_manifest.json",
            virtual_board_path=self.config.board_dir / "virtual_신규상장주.json",
            board_file_sync_service=self._board_file_sync_service,
            board_repository=self._repo,
        )

        self._financial_service = FinancialService(repository=self._financial_repo)
        self._weekly_change_service = WeeklyChangeService(
            drive_adapter=self._drive_adapter,
            folder_id=self.config.weekly_change_folder_id,
            repository=self._weekly_change_repo
        )
        self._stock_split_sync_service = StockSplitSyncService(
            repository=self._stock_split_repo,
            drive_adapter=self._drive_adapter,
            stock_split_folder_id=self.config.stock_split_folder_id
        )


        self._report_service = None
        self._init_report_service()

        # 백그라운드 동기화 기동 (모든 서비스 초기화 완비 후 안전하게 실행)
        self.sync_financial_statements_from_drive()
        self.sync_boards_from_drive_in_background()
        self.sync_stock_splits_from_drive_in_background()
        self.sync_heatmap_from_drive_in_background()

    def _init_google_drive(self):
        """환경 설정 및 보안 파일 확인 후 Google Drive 어댑터를 초기화한다."""
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
        """Google Drive 어댑터가 활성화된 경우 리포트 서비스를 조립한다."""
        if self._drive_adapter and self.config.report_folder_id:
            self._report_service = ReportService(
                cloud_storage=self._drive_adapter,
                local_storage=self._report_storage,
                report_folder_id=self.config.report_folder_id,
                report_dir=str(self.config.report_dir),
            )

    def sync_financial_statements_from_drive(self):
        """Google Drive로부터 재무제표 엑셀 파일을 백그라운드에서 비동기적으로 다운로드하여 동기화합니다.
        (서버 기동 시 블로킹 방지를 위해 백그라운드 스레드로 실행합니다.)
        """
        if not self._drive_adapter or not self.config.financial_statements_id:
            logger.info("[Container] 재무제표 구글 드라이브 ID가 없거나 어댑터가 활성화되지 않아 동기화를 건너뜁니다.")
            return

        import threading

        def run_sync_in_background():
            import asyncio
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                new_loop.run_until_complete(self._sync_financial_statements_async())
            except Exception as e:
                logger.error(f"[Container] 백그라운드 재무제표 동기화 실패: {e}")
            finally:
                new_loop.close()

        # 완전한 논블로킹(Non-blocking) 백그라운드 데몬 스레드로 실행
        t = threading.Thread(target=run_sync_in_background, name="FinancialSyncThread", daemon=True)
        t.start()
        logger.info("[Container] 백그라운드 재무제표 동기화 스레드를 성공적으로 시작했습니다.")

    def sync_boards_from_drive_in_background(self):
        """Google Drive로부터 가상/테마 보드 파일을 백그라운드 스레드에서 양방향 동기화합니다."""
        if not self._drive_adapter or not self.config.theme_folder_id:
            logger.info("[Container] 가상/테마 보드 구글 드라이브 폴더 ID가 없거나 어댑터가 활성화되지 않아 동기화를 건너뜁니다.")
            return

        import threading

        def run_sync_in_background():
            import asyncio
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                new_loop.run_until_complete(self._board_file_sync_service.sync_with_drive())
            except Exception as e:
                logger.error(f"[Container] 백그라운드 가상/테마 보드 동기화 실패: {e}")
            finally:
                new_loop.close()

        # 완전한 논블로킹(Non-blocking) 백그라운드 데몬 스레드로 실행
        t = threading.Thread(target=run_sync_in_background, name="BoardSyncThread", daemon=True)
        t.start()
        logger.info("[Container] 백그라운드 가상/테마 보드 동기화 스레드를 성공적으로 시작했습니다.")

    def sync_stock_splits_from_drive_in_background(self):
        """Google Drive로부터 주식 분할(액면분할) 데이터를 백그라운드 스레드에서 다운로드하여 동기화합니다."""
        if not self._drive_adapter or not self.config.stock_split_folder_id:
            logger.info("[Container] 주식 분할 구글 드라이브 폴더 ID가 없거나 어댑터가 활성화되지 않아 동기화를 건너뜁니다.")
            return

        import threading

        def run_sync_in_background():
            import asyncio
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                new_loop.run_until_complete(self._stock_split_sync_service.sync())
            except Exception as e:
                logger.error(f"[Container] 백그라운드 주식 분할 동기화 실패: {e}")
            finally:
                new_loop.close()

        # 완전한 논블로킹(Non-blocking) 백그라운드 데몬 스레드로 실행
        t = threading.Thread(target=run_sync_in_background, name="StockSplitSyncThread", daemon=True)
        t.start()
        logger.info("[Container] 백그라운드 주식 분할 동기화 스레드를 성공적으로 시작했습니다.")

    def sync_heatmap_from_drive_in_background(self):
        """Google Drive로부터 히트맵 테마 JSON 파일들을 백그라운드 스레드에서 동기화합니다."""
        if not self._drive_adapter:
            logger.info("[Container] 어댑터가 활성화되지 않아 히트맵 동기화를 건너뜁니다.")
            return

        import threading

        def run_sync_in_background():
            import asyncio
            from synapstock.application.services.heatmap.heatmap_service import HeatmapService
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                svc = HeatmapService()
                new_loop.run_until_complete(svc.sync_from_drive())
            except Exception as e:
                logger.error(f"[Container] 백그라운드 히트맵 동기화 실패: {e}")
            finally:
                new_loop.close()

        # 완전한 논블로킹(Non-blocking) 백그라운드 데몬 스레드로 실행
        t = threading.Thread(target=run_sync_in_background, name="HeatmapSyncThread", daemon=True)
        t.start()
        logger.info("[Container] 백그라운드 히트맵 동기화 스레드를 성공적으로 시작했습니다.")


    async def _sync_financial_statements_async(self):
        import os
        from datetime import datetime

        file_id = self.config.financial_statements_id
        local_path = self.config.financial_dir / "재무제표.xlsx"

        logger.info(f"[Container] 재무제표 구글 드라이브 동기화 검사 시작 (ID: {file_id})")

        # 1. 구글 드라이브 ID 메타데이터 조회
        meta = await self._drive_adapter.get_file_metadata(file_id)
        if not meta:
            logger.error("[Container] 구글 드라이브에서 재무제표 메타데이터를 가져오지 못했습니다.")
            return

        mime_type = meta.get("mimeType", "")
        target_file_id = file_id
        target_modified_time_str = meta.get("modifiedTime")
        target_mime_type = mime_type

        # 2. 만약 폴더 ID인 경우, 폴더 내부에서 '재무제표' 이름을 포함한 최신 엑셀/스프레드시트 파일을 검색
        if mime_type == "application/vnd.google-apps.folder":
            logger.info(f"[Container] 제공된 ID가 폴더이므로 폴더 내부를 검색합니다.")

            def _find_file_in_folder():
                try:
                    query = (
                        f"'{file_id}' in parents and trashed = false and "
                        f"(mimeType = 'application/vnd.google-apps.spreadsheet' or "
                        f"mimeType = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')"
                    )
                    results = self._drive_adapter.service.files().list(
                        q=query,
                        fields="files(id, name, modifiedTime, mimeType)",
                        orderBy="modifiedTime desc"
                    ).execute()
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
            selected_file = None
            for f in files:
                if "재무제표" in f.get("name", ""):
                    selected_file = f
                    break

            if not selected_file:
                selected_file = files[0]  # 검색된 최신 파일 선택

            target_file_id = selected_file["id"]
            target_modified_time_str = selected_file.get("modifiedTime")
            target_mime_type = selected_file.get("mimeType")
            logger.info(f"[Container] 동기화 대상 파일 발견: {selected_file.get('name')} (ID: {target_file_id}, MimeType: {target_mime_type})")

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
            data = await self._drive_adapter.get_file_by_id(target_file_id)
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

    # ── Property 접근자 (Read-only) ──────────────────────────────────────────

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
    def krx_adapter(self) -> NativeKrxAdapter:
        return self._krx_adapter

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


# 전역 컨테이너 인스턴스 생성
container = Container()
