import logging
from typing import Any

from evenezer.application.services.base_statistics_service import BaseStatisticsService
from evenezer.domain.statistics.models import WeeklyChangeReport
from evenezer.infrastructure.parsers.excel.weekly_change import WeeklyChangeParser

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

    async def _load_manifest_by_year_and_type(self, year: int, is_monthly: bool) -> dict | None:
        """구글 드라이브에서 연도별 주간/월간 매니페스트를 로드합니다."""
        if not self.drive_adapter:
            return None
        m_type = "monthly" if is_monthly else "weekly"
        filename = f"{year}/{m_type}_event_manifest_{year}.json"
        try:
            content = await self.drive_adapter.get_file(filename, folder="weekly_change")
            if content:
                import json
                return json.loads(content.decode('utf-8'))
        except Exception as e:
            logger.debug(f"[{self.get_service_name()}] {filename} 로드 실패: {e}")
        return None

    async def _load_manifest(self) -> dict | None:
        """하위 호환성 유지를 위해 루트 event_manifest.json 조회를 시도합니다."""
        if not self.drive_adapter:
            return None
        try:
            content = await self.drive_adapter.get_file("event_manifest.json", folder="weekly_change")
            if content:
                import json
                return json.loads(content.decode('utf-8'))
        except Exception as e:
            logger.warning(f"[{self.get_service_name()}] event_manifest.json 로드 실패: {e}")
        return None

    def _get_full_week_range(self, year: int, week_num: int) -> str:
        """연도와 주차를 바탕으로 해당 주의 월요일~금요일 날짜(MMDD~MMDD)를 계산합니다."""
        import datetime
        d = datetime.date(year, 1, 4)  # 1월 4일은 항상 첫 번째 주에 포함됨
        target_date = d + datetime.timedelta(weeks=week_num - 1)
        monday = target_date - datetime.timedelta(days=target_date.weekday())
        friday = monday + datetime.timedelta(days=4)
        return f"{monday.strftime('%m%d')}~{friday.strftime('%m%d')}"

    async def sync_data(self, date_str: str | None = None) -> WeeklyChangeReport | None:
        """연도별 매니페스트 정보를 기반으로 주간 및 월간 등락률 데이터를 동기화합니다."""
        if not self.drive_adapter:
            return None

        target_event = None
        is_monthly = False
        target_year = None

        if date_str:
            try:
                target_year = int(date_str[:4])
            except Exception:
                import datetime
                target_year = datetime.datetime.now().year

            # 주간 매니페스트 검색
            w_manifest = await self._load_manifest_by_year_and_type(target_year, is_monthly=False)
            if w_manifest:
                for event in w_manifest.values():
                    if event.get("last_trading_day") == date_str:
                        target_event = event
                        is_monthly = False
                        break
            
            # 주간에서 못 찾았으면 월간 매니페스트 검색
            if not target_event:
                m_manifest = await self._load_manifest_by_year_and_type(target_year, is_monthly=True)
                if m_manifest:
                    for event in m_manifest.values():
                        if event.get("last_trading_day") == date_str:
                            target_event = event
                            is_monthly = True
                            break
        else:
            import datetime
            current_year = datetime.datetime.now().year
            years_to_try = [current_year, current_year - 1]
            
            all_events = []
            for y in years_to_try:
                w_m = await self._load_manifest_by_year_and_type(y, is_monthly=False)
                if w_m:
                    for ev in w_m.values():
                        if ev.get("status") in ("COMPLETED", "FINAL"):
                            all_events.append((ev, False))
                m_m = await self._load_manifest_by_year_and_type(y, is_monthly=True)
                if m_m:
                    for ev in m_m.values():
                        if ev.get("status") in ("COMPLETED", "FINAL"):
                            all_events.append((ev, True))
            
            if all_events:
                sorted_events = sorted(all_events, key=lambda x: x[0].get("last_trading_day", ""), reverse=True)
                target_event, is_monthly = sorted_events[0]
                target_year = target_event.get("year")

        if target_event and target_year:
            year = target_event.get("year")
            month = target_event.get("month")
            
            raw_filename = target_event.get("filename", "").replace(".parquet", ".xlsx")
            corrected_filename = raw_filename

            if not is_monthly:
                week_num = target_event.get("week")
                full_range = self._get_full_week_range(year, week_num)
                import re
                corrected_filename = re.sub(r"\d{4}~\d{4}", full_range, raw_filename)

            sub_path = f"{year}/{month:02d}월"
            full_path = f"{sub_path}/{corrected_filename}"

            logger.info(f"[{self.get_service_name()}] 경로/파일명 교정 후 핀포인트 동기화: {full_path}")
            content = await self.drive_adapter.get_file(full_path, folder="weekly_change")

            if content:
                corrected_date = target_event.get("last_trading_day")
                report = self.parser.parse(content, filename=corrected_filename, date=corrected_date)
                self.repository.save_report(report)
                return report

        logger.info(f"[{self.get_service_name()}] 매니페스트 기반 탐색 실패, 기존 재귀 탐색 수행")
        return await self._sync_data_fallback(date_str)

    async def _sync_data_fallback(self, date_str: str | None = None) -> WeeklyChangeReport | None:
        """기존의 폴더 재귀 탐색 방식 (05월 구조 반영)"""
        search_paths = [""]
        if date_str and len(date_str) >= 7:
            search_paths.insert(0, f"{date_str[:4]}/{date_str[5:7]}월")

        files = []
        for path in search_paths:
            found = await self.drive_adapter.list_files_in_folder(path, folder="weekly_change")
            if found:
                valid = [
                    f for f in found
                    if f["name"].lower().endswith((".xlsx", ".xls"))
                    and not f["name"].startswith("~$")
                    and ("weekly_gainers" in f["name"].lower() or "monthly_gainers" in f["name"].lower())
                ]
                if date_str and date_str[:4]:
                    valid = [f for f in valid if date_str[:4] in f["name"]]
                if valid:
                    files.extend(valid)
                    if path != "":
                        break

        if not files:
            return None
        latest_file = sorted(files, key=lambda x: x["name"], reverse=True)[0]
        content = await self.drive_adapter.get_file(latest_file["name"], folder="weekly_change")
        if not content:
            return None
        report = self.parser.parse(content, filename=latest_file["name"], date=date_str)
        self.repository.save_report(report)
        return report

    async def list_available_dates(self) -> list[dict[str, Any]]:
        """매니페스트를 로드하여 모든 가용 날짜 목록을 가져옵니다."""
        results_map = {}

        # 1. 로컬 데이터 먼저 로드
        local_dates = self.repository.list_available_dates()
        for d in local_dates:
            report = self.repository.load_report(d)
            if report:
                results_map[report.date] = {
                    "date": report.date,
                    "year": report.year,
                    "month": report.month,
                    "week_of_month": report.week_of_month,
                    "week_num": report.week_num,
                    "date_range": report.date_range,
                    "is_monthly": report.is_monthly,
                    "source": "local"
                }

        # 2. 최근 수년간의 연도별 주간/월간 매니페스트 로드 및 병합
        import datetime
        current_year = datetime.datetime.now().year
        years_to_scan = [current_year, current_year - 1, current_year - 2]
        
        for y in years_to_scan:
            # 주간 매니페스트
            w_manifest = await self._load_manifest_by_year_and_type(y, is_monthly=False)
            if w_manifest:
                for event in w_manifest.values():
                    if event.get("status") not in ("COMPLETED", "FINAL"):
                        continue
                    date_str = event.get("last_trading_day")
                    if date_str and date_str not in results_map:
                        filename = event.get("filename", "")
                        results_map[date_str] = {
                            "date": date_str,
                            "year": event.get("year"),
                            "month": event.get("month"),
                            "week_of_month": event.get("week_of_month"),
                            "week_num": event.get("week"),
                            "date_range": self.parser.extract_metadata_from_filename(filename).get("date_range"),
                            "is_monthly": False,
                            "source": "cloud"
                        }
            
            # 월간 매니페스트
            m_manifest = await self._load_manifest_by_year_and_type(y, is_monthly=True)
            if m_manifest:
                for event in m_manifest.values():
                    if event.get("status") not in ("COMPLETED", "FINAL"):
                        continue
                    date_str = event.get("last_trading_day")
                    if date_str and date_str not in results_map:
                        filename = event.get("filename", "")
                        results_map[date_str] = {
                            "date": date_str,
                            "year": event.get("year"),
                            "month": event.get("month"),
                            "week_of_month": 0,
                            "week_num": 0,
                            "date_range": self.parser.extract_metadata_from_filename(filename).get("date_range"),
                            "is_monthly": True,
                            "source": "cloud"
                        }
        return sorted(results_map.values(), key=lambda x: x["date"], reverse=True)
