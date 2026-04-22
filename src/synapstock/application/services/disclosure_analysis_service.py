import logging
from synapstock.infrastructure.parsers.excel import DisclosureParser
from synapstock.application.services.base_statistics_service import BaseStatisticsService

logger = logging.getLogger(__name__)

class DisclosureAnalysisService(BaseStatisticsService):
    """유무상증자, CB, BW 등 공시 데이터 분석 전문 서비스."""

    def __init__(self, drive_adapter, folder_id, local_repository):
        super().__init__(drive_adapter, folder_id)
        self.repository = local_repository
        self.parser = DisclosureParser()

    def get_service_name(self) -> str:
        return "DisclosureAnalysisService"

    def get_data(self, dataType: str, year: str) -> list:
        """데이터 타입별 조회를 처리합니다."""
        fetcher = {
            "capital_increase": getattr(self.repository, "get_capital_increase_data", lambda x: []),
            "bonus_issue": getattr(self.repository, "get_bonus_issue_data", lambda x: []),
            "cb": getattr(self.repository, "get_convertible_bond_data", lambda x: []),
            "bw": getattr(self.repository, "get_bw_data", lambda x: [])
        }
        items = fetcher.get(dataType, lambda x: [])(year)
        if not items:
            return self.sync_data(dataType, year)
        return items

    def sync_data(self, dataType: str, year: str) -> list:
        """각 공시 정보별 동기화 로직을 실행합니다."""
        mapping = {
            "capital_increase": ("증자", "capital_increase", self.parser.parse_paid_in_capital_increase, getattr(self.repository, "save_capital_increase_data", lambda x: None)),
            "bonus_issue": ("배당", "bonus_issue", self.parser.parse_bonus_issue, getattr(self.repository, "save_bonus_issue_data", lambda x: None)),
            "cb": ("CB", "convertible_bond", self.parser.parse_convertible_bond, getattr(self.repository, "save_convertible_bond_data", lambda x: None)),
            "bw": ("BW", "bw", self.parser.parse_bond_with_warrants, getattr(self.repository, "save_bw_data", lambda x: None))
        }
        
        if dataType not in mapping:
            return []
            
        pattern, folder, parser, saver = mapping[dataType]
        return self._sync_domain_data(
            year_str=year,
            filename_pattern=pattern,
            parser_func=parser,
            save_func=saver,
            folder_name=folder
        )
