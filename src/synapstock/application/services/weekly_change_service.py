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
        # 주간 등락률 전용: 연도/월 하위 폴더 기반 동기화 로직
        if not self.drive_adapter:
            return None

        # 1. 하위 폴더 경로 생성 (예: 2026/05)
        sub_path = ""
        if date_str and len(date_str) >= 7:
            sub_path = f"{date_str[:4]}/{date_str[5:7]}"

        # 2. 파일 목록 조회 (하위 폴더 우선, 없으면 루트)
        files = []
        if sub_path:
            logger.info(f"[{self.get_service_name()}] 하위 폴더 검색: {sub_path}")
            files = await self.drive_adapter.list_files_in_folder(sub_path, folder="weekly_change")
        
        if not files:
            files = await self.drive_adapter.list_files_in_folder("", folder="weekly_change")

        # 3. 유효 파일 필터링 및 최신 파일 선택
        valid_files = [f for f in files if f["name"].lower().endswith((".xlsx", ".xls")) and not f["name"].startswith("~$")]
        
        # 연도 필터링
        year_str = date_str[:4] if date_str else None
        if year_str:
            valid_files = [f for f in valid_files if year_str in f["name"]]
            
        if not valid_files:
            logger.warning(f"[{self.get_service_name()}] 유효한 엑셀 파일을 찾을 수 없습니다.")
            return None

        latest_file = sorted(valid_files, key=lambda x: x["name"], reverse=True)[0]

        # 4. 다운로드 및 파싱
        content = await self.drive_adapter.get_file(latest_file["name"], folder="weekly_change")
        if not content:
            return None

        report = self.parser.parse(content, filename=latest_file["name"], date=date_str)
        self.repository.save_report(report)
        
        logger.info(f"[{self.get_service_name()}] {latest_file['name']} 동기화 완료")
        return report

    async def list_available_dates(self) -> list[str]:
        """로컬 저장소의 가용 날짜 목록을 반환합니다."""
        return self.repository.list_available_dates()
