import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Generic, TypeVar

from evenezer.domain.statistics.models import BaseModel

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

class BaseStatisticsService(ABC, Generic[T]):
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

            # 1. 파일 목록 조회 및 기본 확장자 필터링
            if folder_name:
                files = await self.drive_adapter.list_files_in_folder("", folder=folder_name)
            else:
                files = await self.drive_adapter.list_files(self.folder_id)

            # 유효한 엑셀 파일만 필터링 (NFC 정규화 적용)
            import unicodedata
            valid_files = []
            for f in files:
                name_nfc = unicodedata.normalize("NFC", f["name"])
                if name_nfc.lower().endswith((".xlsx", ".xls")) and not name_nfc.startswith("~$"):
                    f_copy = dict(f)
                    f_copy["name_nfc"] = name_nfc
                    valid_files.append(f_copy)

            if not valid_files:
                logger.warning(f"[{self.get_service_name()}] 폴더({folder_name or 'Root'})에 유효한 엑셀 파일이 없습니다.")
                return []

            # 2. 단계별 필터링 (키워드 -> 연도)
            target_files = valid_files

            # 키워드 필터링 (주어진 경우)
            if filename_pattern:
                nfc_pattern = unicodedata.normalize("NFC", filename_pattern)
                filtered_by_pattern = [f for f in target_files if nfc_pattern in f["name_nfc"]]
                if filtered_by_pattern:
                    target_files = filtered_by_pattern

            # 연도 필터링 (주어진 경우, 가급적 해당 연도 파일을 찾음)
            if year_str:
                filtered_by_year = [f for f in target_files if year_str in f["name_nfc"]]
                if filtered_by_year:
                    target_files = filtered_by_year
                else:
                    logger.info(f"[{self.get_service_name()}] 파일명에 연도({year_str})가 포함된 파일이 없어 전체 파일 중 최신본을 선택합니다.")

            # 3. 최신 파일 선택
            latest_file = sorted(target_files, key=lambda x: x["name"], reverse=True)[0]

            # --- 스마트 캐싱 검증 ---
            drive_mtime = 0.0
            if "modifiedTime" in latest_file:
                try:
                    # Drive 시간 파싱 (UTC -> datetime -> timestamp)
                    drive_dt = datetime.fromisoformat(latest_file["modifiedTime"].replace("Z", "+00:00"))
                    drive_mtime = drive_dt.timestamp()
                except Exception as ex:
                    logger.warning(f"[{self.get_service_name()}] Drive 수정 시간 파싱 실패: {ex}")

            if local_cache_path and drive_mtime > 0:
                local_path_obj = Path(local_cache_path)
                if local_path_obj.exists():
                    local_mtime = os.path.getmtime(local_path_obj)
                    # 드라이브 파일의 mtime보다 로컬 캐시가 같거나 더 최신인 경우(1초 내 오차 허용) 다운로드 생략
                    if (local_mtime - drive_mtime) >= -1.0:
                        logger.info(f"[{self.get_service_name()}] 로컬 캐시가 최신 상태입니다. 다운로드를 생략합니다: {latest_file['name']} (Local: {local_mtime}, Drive: {drive_mtime})")
                        print(f"[{self.get_service_name()}] 로컬 캐시가 최신 상태입니다. 다운로드를 생략합니다: {latest_file['name']}")
                        if load_cache_func:
                            cached_data = load_cache_func()
                            if cached_data:
                                return cached_data if isinstance(cached_data, list) else [cached_data]
                            
            # 4. 파일 다운로드
            if folder_name:
                content = await self.drive_adapter.get_file(latest_file["name"], folder=folder_name)
            else:
                content = await self.drive_adapter.download_file(latest_file["id"])

            if not content:
                logger.error(f"[{self.get_service_name()}] 파일을 다운로드할 수 없습니다: {latest_file['name']}")
                return []

            # 5. 파싱 및 저장
            result = parser_func(content, filename=latest_file["name"], **kwargs)
            save_func(result)

            # 다운로드 성공 시 로컬 캐시 파일의 mtime을 드라이브와 일치시킴
            if local_cache_path and drive_mtime > 0:
                try:
                    local_path_obj = Path(local_cache_path)
                    if local_path_obj.exists():
                        os.utime(local_path_obj, (drive_mtime, drive_mtime))
                except Exception as ex:
                    logger.warning(f"[{self.get_service_name()}] 로컬 캐시 파일 수정 시간 동기화 실패: {ex}")

            # 결과가 리스트가 아닌 단일 객체일 경우 처리
            is_list = isinstance(result, list)
            items_count = len(result) if is_list else 1

            logger.info(f"[{self.get_service_name()}] {latest_file['name']} 동기화 완료: {items_count}건")
            return result if is_list else [result]
        except Exception as e:
            logger.error(f"[{self.get_service_name()}] 동기화 중 오류 발생: {e}", exc_info=True)
            return []
