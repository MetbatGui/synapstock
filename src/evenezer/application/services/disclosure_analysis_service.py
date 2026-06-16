import logging
from typing import Any

from evenezer.application.services.base_statistics_service import BaseStatisticsService
from evenezer.infrastructure.parsers.excel import DisclosureParser

logger = logging.getLogger(__name__)

class DisclosureAnalysisService(BaseStatisticsService):
    """[DEPRECATED] 유무상증자, CB, BW 등 공시 데이터 분석 전문 서비스. (무상증자 외 기능 비활성화)"""

    def __init__(self, drive_adapter, folder_id, local_repository):
        super().__init__(drive_adapter, folder_id)
        self.repository = local_repository
        self.parser = DisclosureParser()

    def get_service_name(self) -> str:
        return "DisclosureAnalysisService"

    async def get_data(self, dataType: str, year: str, force_sync: bool = False) -> list:
        """데이터 타입별 조회를 처리합니다."""
        if dataType in ["capital_increase", "cb", "bw"]:
            return []

        if force_sync:
            return await self.sync_data(dataType, year)

        fetcher = {
            "capital_increase": getattr(self.repository, "get_capital_increase_data", lambda x: []),
            "bonus_issue": getattr(self.repository, "get_bonus_issue_data", lambda x: []),
            "cb": getattr(self.repository, "get_convertible_bond_data", lambda x: []),
            "bw": getattr(self.repository, "get_bw_data", lambda x: [])
        }
        items = fetcher.get(dataType, lambda x: [])(year)
        if not items:
            return await self.sync_data(dataType, year)
        return items

    async def sync_data(self, dataType: str, year: str) -> list:
        """각 공시 정보별 동기화 로직을 실행합니다."""
        if dataType in ["capital_increase", "cb", "bw"]:
            logger.warning(f"[{self.get_service_name()}] {dataType} 기능은 현재 비활성화되어 리소스를 할당하지 않습니다.")
            return []

        mapping = {
            "capital_increase": ("유상증자", "capital_increase", self.parser.parse_paid_in_capital_increase, getattr(self.repository, "save_capital_increase_data", lambda x: None)),
            "bonus_issue": ("무상증자", "bonus_issue", self.parser.parse_bonus_issue, getattr(self.repository, "save_bonus_issue_data", lambda x: None)),
            "cb": ("전환사채", "convertible_bond", self.parser.parse_convertible_bond, getattr(self.repository, "save_convertible_bond_data", lambda x: None)),
            "bw": ("신주인수권부사채", "bw", self.parser.parse_bond_with_warrants, getattr(self.repository, "save_bw_data", lambda x: None))
        }

        if dataType not in mapping:
            return []

        pattern, folder, parser, saver = mapping[dataType]
        return await self._sync_domain_data(
            filename_pattern=pattern,
            parser_func=parser,
            save_func=saver,
            folder_name=folder
        )

    async def _sync_domain_data(
        self,
        filename_pattern: str,
        parser_func: Any,
        save_func: Any,
        folder_name: str
    ) -> list:
        """공시 데이터 전용 동기화 로직 (연도 필터링을 하지 않고 파일명 패턴으로만 최신 파일을 찾습니다)."""
        try:
            if not self.drive_adapter:
                logger.warning(f"[{self.get_service_name()}] Drive 어댑터가 설정되지 않았습니다.")
                return []

            files = await self.drive_adapter.list_files_in_folder("", folder=folder_name)
            valid_files = [f for f in files if f["name"].lower().endswith((".xlsx", ".xls")) and not f["name"].startswith("~$")]

            if not valid_files:
                logger.warning(f"[{self.get_service_name()}] 폴더({folder_name})에 유효한 엑셀 파일이 없습니다.")
                return []

            target_files = [f for f in valid_files if filename_pattern in f["name"]]
            if not target_files:
                logger.warning(f"[{self.get_service_name()}] 폴더({folder_name})에 '{filename_pattern}' 패턴의 파일이 없습니다.")
                return []

            latest_file = sorted(target_files, key=lambda x: x["name"], reverse=True)[0]
            content = await self.drive_adapter.get_file(latest_file["name"], folder=folder_name)

            if not content:
                logger.error(f"[{self.get_service_name()}] 파일을 다운로드할 수 없습니다: {latest_file['name']}")
                return []

            result = parser_func(content)
            save_func(result)

            is_list = isinstance(result, list)
            items_count = len(result) if is_list else 1

            logger.info(f"[{self.get_service_name()}] {latest_file['name']} 동기화 완료: {items_count}건")
            return result if is_list else [result]
        except Exception as e:
            logger.error(f"[{self.get_service_name()}] 동기화 중 오류 발생: {e}", exc_info=True)
            return []
