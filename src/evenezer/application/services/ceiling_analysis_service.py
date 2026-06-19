import io
import logging
import re
from datetime import datetime

import pandas as pd

from evenezer.application.services.base_statistics_service import BaseStatisticsService
from evenezer.domain.statistics.models import CeilingAnalysisReport
from evenezer.infrastructure.parsers.excel import CeilingParser

logger = logging.getLogger(__name__)


class CeilingAnalysisService(BaseStatisticsService[CeilingAnalysisReport]):
    """상한가 분석 데이터를 관리하고 제공하는 서비스."""

    def __init__(self, drive_adapter, folder_id, local_repository):
        super().__init__(drive_adapter, folder_id)
        self.repository = local_repository
        self.parser = CeilingParser()

    def get_service_name(self) -> str:
        return "CeilingAnalysisService"

    async def get_ceiling_analysis(self, date: str | None = None, force_sync: bool = False) -> CeilingAnalysisReport | None:
        """스마트 동기화 로직을 적용하여 상한가 리포트를 조회합니다."""
        # 1. 날짜 기본값 및 포맷 정리
        date_norm, year, target_mmdd = self._prepare_dates(date)
        today_str = datetime.now().strftime("%Y-%m-%d")

        # 2. 동기화 필요 여부 판단
        should_sync = await self._check_sync_necessity(year, today_str, force_sync)

        reports: list[CeilingAnalysisReport] = []

        # 3. 로컬 캐시 로드
        if not should_sync:
            reports = self._load_local_reports(date_norm, year, target_mmdd)
            if not reports:
                should_sync = True

        # 4. 동기화 실행
        if should_sync:
            reports = await self._perform_sync(date_norm)

        if not reports:
            logger.warning(f"[{self.get_service_name()}] 동기화된 리포트가 없습니다.")
            return None

        # 5. 결과 필터링 및 정밀 매칭
        return self._filter_and_slice_report(reports, date_norm, target_mmdd)

    def _prepare_dates(self, date: str | None) -> tuple[str, str, str]:
        """날짜 기본값 및 포맷을 정리하여 (date, year, target_mmdd) 튜플을 반환합니다."""
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")
        year = date[:4]
        try:
            parts = date.split('-')
            target_mmdd = f"{int(parts[1]):02d}-{int(parts[2]):02d}"
        except (IndexError, ValueError):
            target_mmdd = date[5:10]
        return date, year, target_mmdd

    async def _check_sync_necessity(self, year: str, today_str: str, force_sync: bool) -> bool:
        """메타데이터 로드 및 클라우드 상태 체크를 통해 동기화 필요 여부를 판별합니다."""
        metadata = self.repository.load_metadata()
        last_synced_at = metadata.get("last_synced_at", "1970-01-01T00:00:00Z")
        latest_data_date = metadata.get("latest_data_date", "")

        should_sync = force_sync

        cloud_file_info = await self._get_cloud_file_info(year)
        if cloud_file_info:
            modified_time = cloud_file_info.get("modifiedTime", "")
            if modified_time > last_synced_at and latest_data_date != today_str:
                logger.info(f"[{self.get_service_name()}] 클라우드 파일 갱신 감지. (Cloud: {modified_time} > Sync: {last_synced_at})")
                should_sync = True
        return should_sync

    def _load_local_reports(self, date: str, year: str, target_mmdd: str) -> list[CeilingAnalysisReport]:
        """로컬 저장소에서 1차/2차 캐시 리포트 조회를 시도합니다."""
        report = self.repository.load_report(date)
        if report:
            return [report]

        available_dates = self.repository.list_available_dates()
        year_dates = [d for d in available_dates if d.startswith(year)]
        if year_dates:
            latest_report = self.repository.load_report(year_dates[0])
            if latest_report:
                normalized_dates = [d.replace(' ', '') for d in latest_report.dates]
                if target_mmdd in normalized_dates:
                    return [latest_report]
        return []

    async def _perform_sync(self, date: str) -> list[CeilingAnalysisReport]:
        """클라우드 동기화를 실행하고 동기화 메타데이터를 저장 및 업데이트합니다."""
        logger.info(f"[{self.get_service_name()}] 데이터 동기화 시작 (대상: {date})")
        reports = await self.sync_data(date)
        if reports:
            new_latest_date = sorted([r.end_date for r in reports], reverse=True)[0]
            self.repository.save_metadata({
                "last_synced_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "latest_data_date": new_latest_date
            })
        return reports

    def _filter_and_slice_report(
        self, reports: list[CeilingAnalysisReport], date: str, target_mmdd: str
    ) -> CeilingAnalysisReport | None:
        """기준일 매칭 또는 최신 시트 포함 여부를 검증하고 필요시 데이터를 슬라이싱하여 반환합니다."""
        # 1순위: 요청 날짜와 리포트 기준일(시트명)이 정확히 일치하는 경우
        for r in reports:
            if r.end_date == date:
                normalized_dates = [d.replace(' ', '') for d in r.dates]
                if target_mmdd in normalized_dates:
                    logger.info(f"[{self.get_service_name()}] 정확한 시트 매칭 성공 (전체 시세 반환: {date})")
                    return r

        # 2순위: 다른 날짜 시트 내에 데이터가 포함되어 있는 경우 (최신 시트부터 탐색)
        sorted_reports = sorted(reports, key=lambda x: x.end_date, reverse=True)
        for r in sorted_reports:
            normalized_dates = [d.replace(' ', '') for d in r.dates]
            if target_mmdd in normalized_dates:
                idx = normalized_dates.index(target_mmdd)
                if any(it.closing_prices[idx] > 0 for it in r.items if it.closing_prices):
                    logger.info(f"[{self.get_service_name()}] 보조 매칭 성공 (시트: {r.end_date}, 데이터: {target_mmdd})")
                    return self._slice_report_by_date(r, date, idx)

        logger.warning(f"[{self.get_service_name()}] 모든 리포트에서 {target_mmdd}의 유효한 데이터를 찾을 수 없습니다.")
        return None

    async def _get_cloud_file_info(self, year: str) -> dict | None:
        """클라우드에서 해당 연도의 파일 정보를 조회합니다."""
        if not self.drive_adapter:
            return None
        files = await self.drive_adapter.list_files_in_folder("", folder="ceiling")
        target_files = [f for f in files if year in f["name"] and f["name"].lower().endswith((".xlsx", ".xls"))]
        if not target_files:
            return None
        return sorted(target_files, key=lambda x: x["name"], reverse=True)[0]

    def _slice_report_by_date(self, report: CeilingAnalysisReport, target_date: str, date_idx: int) -> CeilingAnalysisReport:
        """리포트에서 타겟 날짜 이후의 가격 데이터를 제거하여 해당 시점의 뷰를 만듭니다."""
        new_dates = report.dates[:date_idx + 1]
        new_items = []
        for item in report.items:
            new_prices = item.closing_prices[:date_idx + 1]
            new_item = item.model_copy(update={"closing_prices": new_prices})
            new_items.append(new_item)

        return report.model_copy(update={
            "end_date": target_date,
            "dates": new_dates,
            "items": new_items
        })

    async def sync_data(self, date_str: str) -> list[CeilingAnalysisReport]:
        """연간 단위의 상한가 분석 파일 내의 모든 시트 데이터를 한꺼번에 동기화하여 캐싱합니다."""
        year = date_str[:4]
        save_func = getattr(self.repository, "save_report", lambda x: None)

        return await self._sync_domain_data(
            year_str=year,
            filename_pattern="상한가",
            parser_func=self.parser.parse,
            save_func=save_func,
            folder_name="ceiling"
        )

    async def list_available_dates(self, year: str) -> list[str]:
        """특정 연도 엑셀 파일의 시트명(YYMMDD)을 분석하여 날짜 목록을 반환합니다."""
        if not self.drive_adapter:
            return []

        files = await self.drive_adapter.list_files_in_folder("", folder="ceiling")
        target_files = [f for f in files if year in f["name"] and f["name"].lower().endswith((".xlsx", ".xls"))]

        if not target_files:
            return []

        latest_file = sorted(target_files, key=lambda x: x["name"], reverse=True)[0]
        content = await self.drive_adapter.get_file(latest_file["name"], folder="ceiling")

        if not content:
            return []

        try:
            excel = pd.ExcelFile(io.BytesIO(content))
            sheet_names = excel.sheet_names

            full_dates = []
            for sheet in sheet_names:
                if len(sheet) == 6 and sheet.isdigit():
                    full_dates.append(f"20{sheet[:2]}-{sheet[2:4]}-{sheet[4:6]}")

            return sorted(full_dates, reverse=True)
        except Exception as e:
            logger.error(f"[{self.get_service_name()}] 시트 목록 추출 실패: {e}")
            return []

    async def list_available_years(self) -> list[str]:
        """상한가 데이터가 존재하는 모든 연도 목록을 반환합니다."""
        if not self.drive_adapter:
            return []

        files = await self.drive_adapter.list_files_in_folder("", folder="ceiling")
        years = set()
        for f in files:
            name = f["name"]
            if "상한가" in name and name.lower().endswith((".xlsx", ".xls")):
                match = re.search(r"20\d{2}", name)
                if match:
                    years.add(match.group())

        return sorted(list(years), reverse=True)
