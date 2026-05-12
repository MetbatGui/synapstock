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

    async def _load_manifest(self) -> dict | None:
        """구글 드라이브 루트에서 event_manifest.json을 로드합니다."""
        if not self.drive_adapter:
            return None
        try:
            # 루트 폴더에서 직접 manifest 파일 가져오기
            content = await self.drive_adapter.get_file("event_manifest.json", folder="weekly_change")
            if content:
                import json
                return json.loads(content.decode('utf-8'))
        except Exception as e:
            logger.warning(f"[{self.get_service_name()}] 매니페스트 로드 실패: {e}")
        return None

    async def sync_data(self, date_str: str | None = None) -> WeeklyChangeReport | None:
        """매니페스트 정보를 활용하여 데이터를 핀포인트로 동기화합니다."""
        if not self.drive_adapter:
            return None

        manifest = await self._load_manifest()
        
        # 1. 매니페스트가 있으면 핀포인트 검색
        if manifest:
            target_event = None
            if date_str:
                for event in manifest.values():
                    if event.get("last_trading_day") == date_str:
                        target_event = event
                        break
            else:
                # 날짜 미지정 시 가장 최신 COMPLETED 이벤트 선택
                completed = [e for e in manifest.values() if e.get("status") == "COMPLETED"]
                if completed:
                    target_event = sorted(completed, key=lambda x: x.get("last_trading_day", ""), reverse=True)[0]

            if target_event:
                year = target_event.get("year")
                month = target_event.get("month")
                # 드라이브는 xlsx 형식을 사용하므로 확장자 치환
                filename = target_event.get("filename", "").replace(".parquet", ".xlsx")
                # 매니페스트의 연/월 정보로 하위 폴더 경로 구성
                sub_path = f"{year}/{month:02d}"
                full_path = f"{sub_path}/{filename}"
                
                logger.info(f"[{self.get_service_name()}] 매니페스트 기반 핀포인트 동기화: {full_path}")
                content = await self.drive_adapter.get_file(full_path, folder="weekly_change")
                
                if content:
                    report = self.parser.parse(content, filename=filename, date=target_event.get("last_trading_day"))
                    self.repository.save_report(report)
                    return report

        # 2. 매니페스트가 없거나 실패한 경우 기존 재귀 탐색 수행 (Fallback)
        logger.info(f"[{self.get_service_name()}] 매니페스트 기반 탐색 실패, 기존 재귀 탐색 수행")
        return await self._sync_data_fallback(date_str)

    async def _sync_data_fallback(self, date_str: str | None = None) -> WeeklyChangeReport | None:
        """기존의 폴더 재귀 탐색 방식 (매니페스트 없을 때 사용)"""
        search_paths = [""]
        if date_str and len(date_str) >= 7:
            search_paths.insert(0, f"{date_str[:4]}/{date_str[5:7]}")

        files = []
        for path in search_paths:
            found = await self.drive_adapter.list_files_in_folder(path, folder="weekly_change")
            if found:
                valid = [f for f in found if f["name"].lower().endswith((".xlsx", ".xls")) and not f["name"].startswith("~$")]
                if date_str and date_str[:4]:
                    valid = [f for f in valid if date_str[:4] in f["name"]]
                if valid:
                    files.extend(valid)
                    if path != "": break

        if not files: return None
        latest_file = sorted(files, key=lambda x: x["name"], reverse=True)[0]
        content = await self.drive_adapter.get_file(latest_file["name"], folder="weekly_change")
        if not content: return None
        report = self.parser.parse(content, filename=latest_file["name"], date=date_str)
        self.repository.save_report(report)
        return report

    async def list_available_dates(self) -> list[dict[str, Any]]:
        """매니페스트를 로드하여 모든 가용 날짜 목록을 순식간에 가져옵니다."""
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
                    "source": "local"
                }

        # 2. 매니페스트 로드 및 병합 (클라우드 스캔 대체)
        manifest = await self._load_manifest()
        if manifest:
            for event in manifest.values():
                if event.get("status") != "COMPLETED":
                    continue
                
                date_str = event.get("last_trading_day")
                if date_str and date_str not in results_map:
                    # 파일명에서 정보 유추 또는 매니페스트 데이터 사용
                    filename = event.get("filename", "")
                    results_map[date_str] = {
                        "date": date_str,
                        "year": event.get("year"),
                        "month": event.get("month"),
                        "week_of_month": event.get("week_of_month"),
                        "week_num": event.get("week"),
                        "date_range": self.parser.extract_metadata_from_filename(filename).get("date_range"),
                        "source": "cloud"
                    }
        else:
            # 매니페스트가 없는 경우에만 제한적으로 현재 연도만 스캔 (최소한의 안전장치)
            logger.info(f"[{self.get_service_name()}] 매니페스트 없음, 제한적 클라우드 스캔 수행")
            import datetime
            y = datetime.datetime.now().year
            cloud_files = await self.drive_adapter.list_files_in_folder(str(y), folder="weekly_change")
            if cloud_files:
                for f in cloud_files:
                    name = f["name"]
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

        return sorted(results_map.values(), key=lambda x: x["date"], reverse=True)
