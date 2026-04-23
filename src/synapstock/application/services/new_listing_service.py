import logging
from synapstock.domain.statistics.models import NewListing
from synapstock.infrastructure.parsers.excel import NewListingParser
from synapstock.application.services.base_statistics_service import BaseStatisticsService

logger = logging.getLogger(__name__)

class NewListingService(BaseStatisticsService[NewListing]):
    """신규 상장(IPO) 분석 전문 서비스."""

    def __init__(self, drive_adapter, folder_id, local_repository):
        super().__init__(drive_adapter, folder_id)
        self.repository = local_repository
        self.parser = NewListingParser()

    def get_service_name(self) -> str:
        return "NewListingService"

    def get_data(self, year: str, force_sync: bool = False) -> list[NewListing]:
        """로컬에서 데이터를 조회하고, 없거나 force_sync=True이면 클라우드와 수동 동기화를 시도합니다."""
        if force_sync:
            return self.sync_data(year)

        # 신규 상장은 특정 연도 조회가 아닌 전체 또는 연도별 저장을 지원할 수 있음
        # 레포지토리 인터페이스에 맞춰 호출
        if hasattr(self.repository, "get_new_listings"):
            items = self.repository.get_new_listings(year)
            if items:
                return items
        
        return self.sync_data(year)

    def sync_data(self, year: str) -> list[NewListing]:
        """Base 클래스의 동기화 워크플로우를 사용하여 신규 상장 데이터를 업데이트합니다."""
        save_func = getattr(self.repository, "save_new_listings", lambda x: None)
        return self._sync_domain_data(
            year_str=year,
            filename_pattern="신규상장",
            parser_func=self.parser.parse,
            save_func=save_func,
            folder_name="new_listing"
        )
