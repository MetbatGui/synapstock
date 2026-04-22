import logging
import re
from synapstock.domain.statistics.models import CeilingAnalysisReport
from synapstock.infrastructure.parsers.excel import CeilingParser
from synapstock.application.services.base_statistics_service import BaseStatisticsService

logger = logging.getLogger(__name__)

class CeilingAnalysisService(BaseStatisticsService[CeilingAnalysisReport]):
    """상한가 분석 및 리포트 관리 서비스."""

    def __init__(self, drive_adapter, folder_id, local_repository):
        super().__init__(drive_adapter, folder_id)
        self.repository = local_repository
        self.parser = CeilingParser()

    def get_service_name(self) -> str:
        return "CeilingAnalysisService"

    def get_ceiling_analysis(self, date: str) -> CeilingAnalysisReport | None:
        """로컬에서 상한가 리포트를 조회하고, 없으면 동기화합니다."""
        if hasattr(self.repository, "get_ceiling_report"):
            report = self.repository.get_ceiling_report(date)
            if report:
                return self._enrich_report(report)
        
        reports = self.sync_data(date)
        report = next((r for r in reports if r.date == date), None)
        
        if report:
            return self._enrich_report(report)
        return None

    def sync_data(self, date_str: str) -> list[CeilingAnalysisReport]:
        """연간 단위의 상한가 분석 파일에서 특정 날짜 데이터를 동기화합니다."""
        year = date_str[:4]
        save_func = getattr(self.repository, "save_ceiling_reports", lambda x: None)
        return self._sync_domain_data(
            year_str=year,
            filename_pattern="상한가",
            parser_func=self.parser.parse_ceiling_report,
            save_func=save_func,
            folder_name="ceiling_analysis"
        )

    def _enrich_report(self, report: CeilingAnalysisReport) -> CeilingAnalysisReport:
        """리포트에 추가적인 분석 데이터를 보강합니다."""
        # 모델의 computed_field 등으로 대체되거나 필요한 경우 추가 로직 수행
        return report

    def list_available_years(self) -> list[str]:
        """조회 가능한 상한가 분석 연도 목록을 반환합니다."""
        if not self.drive_adapter:
            return []
            
        files = self.drive_adapter.list_files_in_folder("", folder="ceiling_analysis")
        years = set()
        for f in files:
            if "상한가" in f["name"]:
                match = re.search(r"20\d{2}", f["name"])
                if match:
                    years.add(match.group())
        return sorted(list(years), reverse=True)

    def list_available_dates(self, year: str) -> list[str]:
        """특정 연도에 상한가 데이터가 존재하는 날짜 목록을 반환합니다."""
        if hasattr(self.repository, "get_ceiling_reports_by_year"):
            reports = self.repository.get_ceiling_reports_by_year(year)
            if reports:
                return sorted([r.date for r in reports], reverse=True)
                
        # 데이터가 없으면 동기화 시도
        reports = self.sync_data(f"{year}-01-01")
        return sorted([r.date for r in reports], reverse=True)
