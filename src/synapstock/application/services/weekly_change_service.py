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
        if not self.drive_adapter:
            return None

        # 1. 탐색 경로 결정 (날짜가 있으면 해당 연도/월, 없으면 루트 및 전체 탐색)
        search_paths = [""]
        if date_str and len(date_str) >= 7:
            search_paths.insert(0, f"{date_str[:4]}/{date_str[5:7]}")

        files = []
        for path in search_paths:
            logger.info(f"[{self.get_service_name()}] Drive 검색 시도: {path or 'root'}")
            found = await self.drive_adapter.list_files_in_folder(path, folder="weekly_change")
            if found:
                # 유효 파일만 필터링
                valid = [f for f in found if f["name"].lower().endswith((".xlsx", ".xls")) and not f["name"].startswith("~$")]
                # 날짜 필터링 (있을 경우)
                if date_str and date_str[:4]:
                    valid = [f for f in valid if date_str[:4] in f["name"]]
                
                if valid:
                    files.extend(valid)
                    # 특정 경로에서 파일을 찾았으면 중단 (최적화)
                    if path != "":
                        break

        if not files:
            logger.warning(f"[{self.get_service_name()}] 유효한 엑셀 파일을 찾을 수 없습니다.")
            return None

        # 최신 파일 선택
        latest_file = sorted(files, key=lambda x: x["name"], reverse=True)[0]

        # 2. 다운로드 및 파싱
        # 파일이 어느 경로에 있었는지 확인하여 가져오기
        content = await self.drive_adapter.get_file(latest_file["name"], folder="weekly_change")
        if not content:
            return None

        report = self.parser.parse(content, filename=latest_file["name"], date=date_str)
        
        # 3. 로컬 저장 (하위 폴더 구조 적용)
        self.repository.save_report(report)
        
        logger.info(f"[{self.get_service_name()}] {latest_file['name']} 동기화 완료")
        return report

    async def list_available_dates(self) -> list[dict[str, Any]]:
        """로컬 및 클라우드(Drive)의 모든 가용 날짜 목록을 반환합니다."""
        # 1. 로컬 데이터 조회
        local_dates = self.repository.list_available_dates()
        results_map = {} # date -> metadata

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
                    "source": "local"
                }

        # 2. 클라우드 데이터 스캔 (2020~2026 연도별 폴더 탐색)
        if self.drive_adapter:
            import datetime
            import asyncio
            current_year = datetime.datetime.now().year
            years_to_check = range(2020, current_year + 2)
            
            async def scan_folder(path: str):
                """특정 경로에서 파일을 찾아 results_map에 추가 (재귀 호출 가능)"""
                cloud_files = await self.drive_adapter.list_files_in_folder(path, folder="weekly_change")
                if not cloud_files:
                    return

                for f in cloud_files:
                    name = f["name"]
                    mime = f.get("mimeType", "")
                    
                    # 폴더인 경우 (보통 월 폴더) 한 단계 더 탐색
                    if mime == "application/vnd.google-apps.folder":
                        new_path = f"{path}/{name}" if path else name
                        await scan_folder(new_path)
                        continue

                    # 파일인 경우 메타데이터 추출
                    if name.lower().endswith((".xlsx", ".xls")) and "weekly_gainers" in name:
                        meta = self.parser.extract_metadata_from_filename(name)
                        if meta and meta.get("date") != "Unknown":
                            d_str = meta["date"]
                            if d_str not in results_map:
                                results_map[d_str] = {
                                    "date": d_str,
                                    "year": meta["year"],
                                    "month": meta["month"],
                                    "week_of_month": meta["week_of_month"],
                                    "week_num": meta["week_num"],
                                    "date_range": meta["date_range"],
                                    "source": "cloud"
                                }

            # 각 연도별로 탐색 시작
            # (병렬 처리를 하면 빠르지만 API 할당량을 고려하여 순차 또는 제한된 병렬로 수행)
            for y in sorted(years_to_check, reverse=True):
                await scan_folder(str(y))

        return sorted(results_map.values(), key=lambda x: x["date"], reverse=True)
