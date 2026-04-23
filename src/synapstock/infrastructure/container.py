"""SynapStock 전역 의존성 주입(DI) 컨테이너.

애플리케이션의 모든 어댑터와 도메인 서비스의 생명주기를 중앙에서 관리합니다.
웹 서버(FastAPI)와 텔레그램 봇 모두 이 컨테이너를 통해 싱글톤 인스턴스를 공유합니다.
"""

import logging

from synapstock.application.services.analytics_service import AnalyticsService
from synapstock.application.services.command_service import BoardCommandService
from synapstock.application.services.market_data_service import MarketDataService
from synapstock.application.services.media_service import StockMediaService
from synapstock.application.services.query_service import BoardQueryService
from synapstock.application.services.report_service import ReportService
from synapstock.application.services.statistics_service import StatisticsService
from synapstock.application.services.sync_service import BoardSyncService
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
from synapstock.infrastructure.adapters.local.market_data_repo import LocalMarketDataRepository
from synapstock.infrastructure.adapters.local.statistics_repo import (
    LocalBondWithWarrantsRepository,
    LocalBonusIssueRepository,
    LocalCapitalIncreaseRepository,
    LocalCeilingRepository,
    LocalConvertibleBondRepository,
    LocalStatisticsRepository,
)
from synapstock.infrastructure.adapters.miro.miro_mindmap import MiroMindmapAdapter
from synapstock.infrastructure.adapters.scraper.httpx_scraper import (
    HttpxNewsScraperAdapter,
)
from synapstock.infrastructure.adapters.scraper.naver_ticker_adapter import (
    NaverTickerSearchAdapter,
)
from synapstock.infrastructure.config import AppConfig

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
        self.config.capital_increase_dir.mkdir(parents=True, exist_ok=True)
        self.config.bonus_issue_dir.mkdir(parents=True, exist_ok=True)
        self.config.convertible_bond_dir.mkdir(parents=True, exist_ok=True)
        self.config.bw_dir.mkdir(parents=True, exist_ok=True)
        self.config.new_listing_dir.mkdir(parents=True, exist_ok=True)
        (self.config.data_dir / "market" / "raw").mkdir(parents=True, exist_ok=True)

        # 3. 인프라 어댑터 싱글톤
        self._repo = LocalBoardRepository(self.config.board_dir)
        self._miro_adapter = MiroMindmapAdapter(self.config.miro_token)
        self._disclosure_adapter = DartDisclosureAdapter()
        self._financial_adapter = ExcelFinancialDataAdapter(self.config.financial_dir / "financial_data.xlsx")
        self._ticker_search_adapter = NaverTickerSearchAdapter(cache_path=str(self.config.stock_cache_path))
        self._news_scraper_adapter = HttpxNewsScraperAdapter()
        self._krx_adapter = NativeKrxAdapter()

        # 저장소 어댑터 (기존 로컬 파일 시스템 작업 추상화)
        self._report_storage = LocalFileStorageAdapter(self.config.report_dir)
        self._pdf_storage = LocalFileStorageAdapter(self.config.pdf_dir)
        self._statistics_repo = LocalStatisticsRepository(self.config.netbuy_dir)
        self._ceiling_repo = LocalCeilingRepository(self.config.ceiling_dir)
        self._capital_increase_repo = LocalCapitalIncreaseRepository(self.config.capital_increase_dir)
        self._bonus_issue_repo = LocalBonusIssueRepository(self.config.bonus_issue_dir)
        self._convertible_bond_repo = LocalConvertibleBondRepository(self.config.convertible_bond_dir)
        self._bw_repo = LocalBondWithWarrantsRepository(self.config.bw_dir)
        self._market_data_repo = LocalMarketDataRepository(self.config.data_dir / "market" / "raw")

        # 4. 조건부 어댑터 (Google Drive)
        self._drive_adapter = None
        self._init_google_drive()

        # 5. 도메인 유즈케이스 서비스 싱글톤
        self._query_service = BoardQueryService(
            repository=self._repo,
            ticker_search=self._ticker_search_adapter,
            disclosure=self._disclosure_adapter,
            financial=self._financial_adapter,
        )
        self._command_service = BoardCommandService(repository=self._repo)
        self._media_service = StockMediaService(
            repository=self._repo, storage=self._pdf_storage, pdf_dir=str(self.config.pdf_dir)
        )
        self._sync_service = BoardSyncService(mindmap=self._miro_adapter, ticker_search=self._ticker_search_adapter)
        self._market_data_service = MarketDataService(krx_adapter=self._krx_adapter, repository=self._market_data_repo)

        self._analytics_service = AnalyticsService(market_data_repo=self._market_data_repo)

        self._statistics_service = StatisticsService(
            storage=self._drive_adapter,
            repository=self._statistics_repo,
            query_service=self._query_service,
            ceiling_repository=self._ceiling_repo,
            capital_increase_repository=self._capital_increase_repo,
            bonus_issue_repository=self._bonus_issue_repo,
            convertible_bond_repository=self._convertible_bond_repo,
            bw_repository=self._bw_repo,
            market_data_service=self._market_data_service,
        )

        self._report_service = None
        self._init_report_service()

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
                "capital_increase": self.config.capital_increase_folder_id,
                "bonus_issue": self.config.bonus_issue_folder_id,
                "convertible_bond": self.config.convertible_bond_folder_id,
                "bw": self.config.bw_folder_id,
                "new_listing": self.config.new_listing_folder_id,
            }
            self._drive_adapter = GoogleDriveAdapter(
                token_file=str(token_path),
                folders=folders,
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
    def analytics_service(self) -> AnalyticsService:
        return self._analytics_service

    @property
    def market_data_service(self) -> MarketDataService:
        return self._market_data_service

    @property
    def krx_adapter(self) -> NativeKrxAdapter:
        return self._krx_adapter


# 전역 컨테이너 인스턴스 생성
container = Container()
