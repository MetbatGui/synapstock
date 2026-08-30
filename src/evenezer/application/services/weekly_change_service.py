import logging
from datetime import datetime

from evenezer.application.services.base_statistics_service import BaseStatisticsService
from evenezer.domain.statistics.models import WeeklyChangeReport
from evenezer.infrastructure.persistence.weekly_change_db_query import (
    build_report,
    event_date_range,
    fetch_event_by_date,
    fetch_events,
    fetch_latest_event,
)
from evenezer.infrastructure.persistence.weekly_change_db_sync import WeeklyChangeDbSync

logger = logging.getLogger(__name__)

_FINAL_STATUSES = ("COMPLETED", "FINAL")


class WeeklyChangeService(BaseStatisticsService[WeeklyChangeReport]):
    """주간/월간 등락률 데이터를 관리하는 서비스.

    krx-auto-crawling이 발행하는 SQLite SSOT DB(weekly/monthly)를 로컬로 구독해
    조회한다 (docs/db_ssot_consumer_sync.md 참고).
    """

    def __init__(self, drive_adapter, folder_id, repository, db_sync: WeeklyChangeDbSync | None = None):
        super().__init__(drive_adapter, folder_id)
        self.repository = repository
        self.db_sync = db_sync or WeeklyChangeDbSync(drive_adapter)

    def get_service_name(self) -> str:
        return "WeeklyChangeService"

    async def get_weekly_change(self, date: str, force_sync: bool = False) -> WeeklyChangeReport | None:
        """특정 날짜의 주간 등락률 데이터를 가져옵니다.

        force_sync=True면 mindmap 자체 리포트 캐시를 건너뛸 뿐 아니라, DB 동기화의
        TTL(§10.3)도 무시하고 원격과 실제로 대조한다 - 사용자가 명시적으로 새로고침을
        누른 경우까지 20분 TTL에 막혀 낡은 로컬을 보여주면 안 되기 때문이다.
        """
        if not force_sync:
            report = self.repository.load_report(date)
            if report:
                return report

        return await self.sync_data(date, force=force_sync)

    @staticmethod
    def _parse_year(date_str: str) -> int:
        try:
            return int(date_str[:4])
        except (ValueError, TypeError):
            return datetime.now().year

    async def _sync_for_year(self, year: int, date_str: str, force: bool = False) -> WeeklyChangeReport | None:
        """지정 연도의 weekly/monthly DB에서 date_str에 해당하는 이벤트를 찾아 리포트를 조립합니다."""
        for is_monthly in (False, True):
            db_path = await self.db_sync.ensure_year_db(year, is_monthly, force=force)
            if not db_path:
                continue
            event = fetch_event_by_date(db_path, date_str)
            if event:
                report = build_report(db_path, event, is_monthly)
                self.repository.save_report(report)
                return report
        return None

    async def _sync_latest(self, force: bool = False) -> WeeklyChangeReport | None:
        """올해/작년 weekly/monthly DB를 모두 훑어 가장 최근 완료 이벤트를 찾습니다."""
        current_year = datetime.now().year
        candidates = []
        for year in (current_year, current_year - 1):
            for is_monthly in (False, True):
                db_path = await self.db_sync.ensure_year_db(year, is_monthly, force=force)
                if not db_path:
                    continue
                event = fetch_latest_event(db_path)
                if event:
                    candidates.append((event["last_trading_day"], db_path, event, is_monthly))

        if not candidates:
            return None

        candidates.sort(key=lambda c: c[0], reverse=True)
        _, db_path, event, is_monthly = candidates[0]
        report = build_report(db_path, event, is_monthly)
        self.repository.save_report(report)
        return report

    async def sync_data(self, date_str: str | None = None, force: bool = False) -> WeeklyChangeReport | None:
        """SSOT DB를 최신 상태로 동기화하고, 대상 이벤트를 리포트로 조립해 로컬 캐시에 저장합니다.

        force=True면 db_sync의 TTL을 무시하고 항상 원격과 실제로 대조한다(수동 새로고침용).
        """
        if not self.drive_adapter:
            return None

        if date_str:
            return await self._sync_for_year(self._parse_year(date_str), date_str, force=force)
        return await self._sync_latest(force=force)

    def _local_dates(self) -> dict[tuple[str, bool], dict]:
        results = {}
        for d in self.repository.list_available_dates():
            report = self.repository.load_report(d)
            if report:
                results[(report.date, report.is_monthly)] = {
                    "date": report.date,
                    "year": report.year,
                    "month": report.month,
                    "week_of_month": report.week_of_month,
                    "week_num": report.week_num,
                    "date_range": report.date_range,
                    "is_monthly": report.is_monthly,
                    "source": "local",
                }
        return results

    async def _cloud_dates(self, known_keys: set[tuple[str, bool]]) -> dict[tuple[str, bool], dict]:
        """weekly/monthly는 별도 축이므로 (날짜, is_monthly) 조합으로 구분한다.

        월말 마지막 거래일이 그 주의 금요일 마감일과 같은 날짜인 경우가 흔해,
        날짜만으로 중복 판정하면 한쪽이 다른 쪽을 가려버린다.
        """
        results = {}
        current_year = datetime.now().year
        for year in (current_year, current_year - 1, current_year - 2):
            for is_monthly in (False, True):
                db_path = await self.db_sync.ensure_year_db(year, is_monthly)
                if not db_path:
                    continue
                for event in fetch_events(db_path):
                    if event["status"] not in _FINAL_STATUSES:
                        continue
                    date_str = event["last_trading_day"]
                    key = (date_str, is_monthly)
                    if key in known_keys or key in results:
                        continue
                    results[key] = {
                        "date": date_str,
                        "year": event["year"],
                        "month": event["month"],
                        "week_of_month": event["week_of_month"],
                        "week_num": event["week"],
                        "date_range": event_date_range(event),
                        "is_monthly": is_monthly,
                        "source": "cloud",
                    }
        return results

    async def list_available_dates(self) -> list[dict]:
        """로컬 캐시와 원격 SSOT DB를 병합하여 모든 가용 날짜 목록을 가져옵니다."""
        results_map = self._local_dates()

        if self.drive_adapter:
            results_map.update(await self._cloud_dates(set(results_map)))

        return sorted(results_map.values(), key=lambda x: x["date"], reverse=True)
