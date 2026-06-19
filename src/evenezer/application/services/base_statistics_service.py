import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

from evenezer.domain.statistics.models import BaseModel

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

class BaseStatisticsService[T: BaseModel](ABC):
    """통계 서비스의 공통 로직을 처리하는 추상 베이스 클래스."""

    def __init__(self, drive_adapter, folder_id: str):
        self.drive_adapter = drive_adapter
        self.folder_id = folder_id

    @abstractmethod
    def get_service_name(self) -> str:
        """서비스 식별을 위한 이름을 반환합니다."""
        pass

    async def _sync_domain_data(
        self,
        year_str: str | None = None,
        filename_pattern: str | None = None,
        parser_func: Any = None,
        save_func: Any = None,
        folder_name: str | None = None,
        local_cache_path: Path | str | None = None,
        load_cache_func: Any = None,
        **kwargs
    ) -> list[T]:
        """도메인 데이터를 클라우드에서 동기화하는 공통 워크플로우 (유연한 필터링 및 스마트 캐싱 적용)."""
        try:
            if not self.drive_adapter:
                logger.warning(f"[{self.get_service_name()}] Drive 어댑터가 설정되지 않았습니다.")
                return []

            # 1. 파일 목록 조회 및 필터링
            latest_file = await self._fetch_latest_file(folder_name, filename_pattern, year_str)
            if not latest_file:
                return []

            drive_mtime = self._parse_drive_mtime(latest_file)

            # 2. 스마트 캐싱 검증 및 로드
            cached = self._try_load_fresh_cache(local_cache_path, drive_mtime, latest_file["name"], load_cache_func)
            if cached is not None:
                return cached

            # 3. 파일 다운로드
            content = await self._download_file_content(latest_file, folder_name)
            if not content:
                logger.error(f"[{self.get_service_name()}] 파일을 다운로드할 수 없습니다: {latest_file['name']}")
                return []

            # 4. 파싱 및 저장
            result = parser_func(content, filename=latest_file["name"], **kwargs)
            save_func(result)

            # 다운로드 성공 시 로컬 캐시 파일의 mtime을 드라이브와 일치시킴
            self._sync_local_cache_mtime(local_cache_path, drive_mtime)

            # 결과가 리스트가 아닌 단일 객체일 경우 처리
            is_list = isinstance(result, list)
            items_count = len(result) if is_list else 1

            logger.info(f"[{self.get_service_name()}] {latest_file['name']} 동기화 완료: {items_count}건")
            return result if is_list else [result]
        except Exception as e:
            logger.error(f"[{self.get_service_name()}] 동기화 중 오류 발생: {e}", exc_info=True)
            return []

    def _try_load_fresh_cache(
        self, local_cache_path: Path | str | None, drive_mtime: float, filename: str, load_cache_func: Any
    ) -> list[T] | None:
        """로컬 캐시가 최신인 경우 로드된 캐시 리스트를 반환하고, 그렇지 않으면 None을 반환합니다."""
        if self._is_local_cache_fresh(local_cache_path, drive_mtime):
            logger.info(
                f"[{self.get_service_name()}] 로컬 캐시가 최신 상태입니다. 다운로드를 생략합니다: "
                f"{filename} (mtime: {drive_mtime})"
            )
            print(f"[{self.get_service_name()}] 로컬 캐시가 최신 상태입니다. 다운로드를 생략합니다: {filename}")
            if load_cache_func:
                cached_data = load_cache_func()
                if cached_data:
                    return cached_data if isinstance(cached_data, list) else [cached_data]
        return None

    async def _fetch_latest_file(
        self, folder_name: str | None, filename_pattern: str | None, year_str: str | None
    ) -> dict | None:
        """조건에 부합하는 최신 원격 파일 정보를 조회합니다."""
        if folder_name:
            files = await self.drive_adapter.list_files_in_folder("", folder=folder_name)
        else:
            files = await self.drive_adapter.list_files(self.folder_id)

        valid_files = self._filter_valid_excel_files(files)
        if not valid_files:
            logger.warning(f"[{self.get_service_name()}] 폴더({folder_name or 'Root'})에 유효한 엑셀 파일이 없습니다.")
            return None

        target_files = self._filter_files_by_pattern_and_year(valid_files, filename_pattern, year_str)
        if not target_files:
            return None

        # 최신 파일 정렬 후 선택
        return sorted(target_files, key=lambda x: x["name"], reverse=True)[0]

    def _filter_valid_excel_files(self, files: list[dict]) -> list[dict]:
        """유효한 엑셀 파일만 필터링하고 NFC 정규화된 이름을 추가합니다."""
        import unicodedata
        valid_files = []
        for f in files:
            name_nfc = unicodedata.normalize("NFC", f["name"])
            if name_nfc.lower().endswith((".xlsx", ".xls")) and not name_nfc.startswith("~$"):
                f_copy = dict(f)
                f_copy["name_nfc"] = name_nfc
                valid_files.append(f_copy)
        return valid_files

    def _filter_files_by_pattern_and_year(
        self, files: list[dict], filename_pattern: str | None, year_str: str | None
    ) -> list[dict]:
        """패턴 및 연도 조건에 따라 파일 목록을 필터링합니다."""
        import unicodedata
        target_files = files

        # 키워드 필터링
        if filename_pattern:
            nfc_pattern = unicodedata.normalize("NFC", filename_pattern)
            filtered_by_pattern = [f for f in target_files if nfc_pattern in f["name_nfc"]]
            if filtered_by_pattern:
                target_files = filtered_by_pattern

        # 연도 필터링
        if year_str:
            filtered_by_year = [f for f in target_files if year_str in f["name_nfc"]]
            if filtered_by_year:
                target_files = filtered_by_year
            else:
                logger.info(
                    f"[{self.get_service_name()}] 파일명에 연도({year_str})가 포함된 파일이 없어 전체 파일 중 최신본을 선택합니다."
                )
        return target_files

    def _parse_drive_mtime(self, file_info: dict) -> float:
        """파일 정보의 수정 시간을 에포크 타임스탬프로 안전하게 파싱합니다."""
        if "modifiedTime" not in file_info:
            return 0.0
        try:
            drive_dt = datetime.fromisoformat(file_info["modifiedTime"].replace("Z", "+00:00"))
            return drive_dt.timestamp()
        except Exception as ex:
            logger.warning(f"[{self.get_service_name()}] Drive 수정 시간 파싱 실패: {ex}")
            return 0.0

    def _is_local_cache_fresh(self, local_cache_path: Path | str | None, drive_mtime: float) -> bool:
        """로컬 캐시가 드라이브보다 최신인지 여부를 확인합니다."""
        if not local_cache_path or drive_mtime <= 0:
            return False
        local_path_obj = Path(local_cache_path)
        if local_path_obj.exists():
            local_mtime = os.path.getmtime(local_path_obj)
            return (local_mtime - drive_mtime) >= -1.0
        return False

    async def _download_file_content(self, file_info: dict, folder_name: str | None) -> bytes | None:
        """대상 파일의 내용을 구글 드라이브에서 다운로드합니다."""
        if folder_name:
            return await self.drive_adapter.get_file(file_info["name"], folder=folder_name)
        else:
            return await self.drive_adapter.download_file(file_info["id"])

    def _sync_local_cache_mtime(self, local_cache_path: Path | str | None, drive_mtime: float) -> None:
        """로컬 캐시 파일의 mtime을 드라이브와 동기화합니다."""
        if not local_cache_path or drive_mtime <= 0:
            return
        try:
            local_path_obj = Path(local_cache_path)
            if local_path_obj.exists():
                os.utime(local_path_obj, (drive_mtime, drive_mtime))
        except Exception as ex:
            logger.warning(f"[{self.get_service_name()}] 로컬 캐시 파일 수정 시간 동기화 실패: {ex}")
