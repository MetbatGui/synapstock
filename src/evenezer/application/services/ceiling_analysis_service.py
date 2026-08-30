import logging
from datetime import datetime

from evenezer.application.services.base_statistics_service import BaseStatisticsService
from evenezer.domain.statistics.models import CeilingAnalysisReport, CeilingItem
from evenezer.infrastructure.persistence import ceiling_db_query
from evenezer.infrastructure.persistence.yearly_db_sync import YearlyDbSync

logger = logging.getLogger(__name__)


class CeilingAnalysisService(BaseStatisticsService[CeilingAnalysisReport]):
    """상한가 분석 데이터를 관리하고 제공하는 서비스.

    ceiling-tracker가 발행하는 SQLite SSOT DB(db/{year}.db)를 로컬로 구독해
    조회한다 (docs/db_ssot_consumer_sync.md 참고).
    """

    def __init__(self, drive_adapter, folder_id, local_repository, db_sync: YearlyDbSync | None = None):
        super().__init__(drive_adapter, folder_id)
        self.repository = local_repository
        self.db_sync = db_sync or YearlyDbSync(
            drive_adapter=drive_adapter,
            data_root="data/statistics/ceiling/db",
            folder_name="ceiling",
            subfolder="db",
            filename_for_year=lambda year: f"{year}.db",
            required_tables={"cohort_stocks", "price_history"},
        )

    def get_service_name(self) -> str:
        return "CeilingAnalysisService"

    async def get_ceiling_analysis(self, date: str | None = None, force_sync: bool = False) -> CeilingAnalysisReport | None:
        """지정된 날짜(코호트 진입일)의 상한가 분석 리포트를 조회합니다.

        force_sync=True면 로컬 캐시를 건너뛰고 db_sync의 TTL도 무시하고 항상
        원격과 대조한다(수동 새로고침용).
        """
        date_norm = date or datetime.now().strftime("%Y-%m-%d")

        if not force_sync:
            cached = self.repository.load_report(date_norm)
            if cached:
                return cached

        reports = await self.sync_data(date_norm, force=force_sync)
        return self._find_report(reports, date_norm)

    @staticmethod
    def _find_report(reports: list[CeilingAnalysisReport], date_norm: str) -> CeilingAnalysisReport | None:
        return next((r for r in reports if r.end_date == date_norm), None)

    async def sync_data(self, date_str: str, force: bool = False) -> list[CeilingAnalysisReport]:
        """SSOT DB를 최신 상태로 동기화하고, 해당 연도의 모든 코호트를 리포트로 조립합니다."""
        try:
            if not self.drive_adapter:
                return []

            year = int(date_str[:4])
            db_path = await self.db_sync.ensure_db(year, force=force)
            if not db_path:
                return []

            reports: list[CeilingAnalysisReport] = []
            for cohort_date in ceiling_db_query.list_cohort_dates(db_path):
                data = ceiling_db_query.fetch_cohort_report(db_path, cohort_date)
                if not data:
                    continue
                items = [
                    CeilingItem(
                        name=it["stock_name"],
                        entry_tag=it["new_high_status"],
                        closing_prices=it["closing_prices"],
                        ticker=it["stock_code"],
                    )
                    for it in data["items"]
                ]
                reports.append(
                    CeilingAnalysisReport(
                        title=f"상한가 분석 리포트 ({cohort_date})",
                        start_date=cohort_date,
                        end_date=cohort_date,
                        dates=data["dates"],
                        items=items,
                    )
                )

            if reports:
                self.repository.save_report(reports)
            return reports

        except Exception as e:
            logger.error(f"[{self.get_service_name()}] 순위 동기화 실패: {e}", exc_info=True)
            return []

    async def list_available_dates(self, year: str) -> list[str]:
        """지정 연도의 코호트 진입일(cohort_date) 목록을 최신순으로 반환합니다."""
        if not self.drive_adapter:
            return []
        db_path = await self.db_sync.ensure_db(int(year))
        if not db_path:
            return []
        return sorted(ceiling_db_query.list_cohort_dates(db_path), reverse=True)

    async def list_available_years(self) -> list[str]:
        """상한가 DB가 존재하는 모든 연도 목록을 반환합니다 ("ceiling/db" 서브폴더의
        {year}.db 파일명 기준)."""
        if not self.drive_adapter:
            return []
        root_files = await self.drive_adapter.list_files_in_folder("", folder="ceiling")
        db_folder = next((f for f in (root_files or []) if f.get("name") == "db"), None)
        if not db_folder:
            return []
        db_files = await self.drive_adapter.list_files_in_folder("", root_id=db_folder["id"], folder="ceiling")
        years = set()
        for f in db_files or []:
            name = f.get("name", "")
            if name.endswith(".db") and name[:-3].isdigit():
                years.add(name[:-3])
        return sorted(years, reverse=True)
