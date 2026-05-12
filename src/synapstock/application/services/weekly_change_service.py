import logging
from typing import Any
from synapstock.application.services.base_statistics_service import BaseStatisticsService
from synapstock.domain.statistics.models import WeeklyChangeReport
from synapstock.infrastructure.parsers.excel.weekly_change import WeeklyChangeParser

logger = logging.getLogger(__name__)

class WeeklyChangeService(BaseStatisticsService[WeeklyChangeReport]):
    """주간 등락률 데이터를 관리하고 동기화하는 서비스."""

    def __init__(self, drive_adapter, folder_id, repository):
        super().__init__(drive_adapter, folder_id)
        self.repository = repository
        self.parser = WeeklyChangeParser()

    def get_service_name(self) -> str:
        return "WeeklyChangeService"

    async def get_weekly_change(self, date: str, force_sync: bool = False) -> WeeklyChangeReport | None:
        """특정 날짜의 주간 등락률 데이터를 가져옵니다."""
        if not force_sync:
            report = self.repository.load_report(date)
            if report:
                return report

        # 로컬에 없거나 강제 동기화인 경우 Drive에서 확인
        return await self.sync_data(date)

    async def sync_data(self, date_str: str | None = None) -> WeeklyChangeReport | None:
        """Drive의 'weekly_change' 폴더에서 데이터를 동기화합니다."""
        results = await self._sync_domain_data(
            year_str=date_str[:4] if date_str else None,
            folder_name="weekly_change",
            parser_func=lambda content, **kwargs: self.parser.parse(content, date=date_str, **kwargs),
            save_func=self.repository.save_report
        )
        return results[0] if results else None

    async def list_available_dates(self) -> list[str]:
        """로컬 저장소의 가용 날짜 목록을 반환합니다."""
        return self.repository.list_available_dates()
