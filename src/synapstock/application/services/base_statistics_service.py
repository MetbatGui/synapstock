import logging
from abc import ABC, abstractmethod
from typing import TypeVar, Generic, Any
import io
import pandas as pd
from synapstock.domain.statistics.models import BaseModel

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

    def _sync_domain_data(
        self, 
        year_str: str | None = None, 
        filename_pattern: str | None = None, 
        parser_func: Any = None,
        save_func: Any = None,
        folder_name: str | None = None,
        **kwargs
    ) -> list[T]:
        """도메인 데이터를 클라우드에서 동기화하는 공통 워크플로우 (유연한 필터링 적용)."""
        try:
            if not self.drive_adapter:
                logger.warning(f"[{self.get_service_name()}] Drive 어댑터가 설정되지 않았습니다.")
                return []

            # 1. 파일 목록 조회 및 기본 확장자 필터링
            if folder_name:
                files = self.drive_adapter.list_files_in_folder("", folder=folder_name)
            else:
                files = self.drive_adapter.list_files(self.folder_id)

            # 유효한 엑셀 파일만 필터링
            valid_files = [f for f in files if f["name"].lower().endswith((".xlsx", ".xls")) and not f["name"].startswith("~$")]
            
            if not valid_files:
                logger.warning(f"[{self.get_service_name()}] 폴더({folder_name or 'Root'})에 유효한 엑셀 파일이 없습니다.")
                return []

            # 2. 단계별 필터링 (키워드 -> 연도)
            target_files = valid_files
            
            # 키워드 필터링 (주어진 경우)
            if filename_pattern:
                filtered_by_pattern = [f for f in target_files if filename_pattern in f["name"]]
                if filtered_by_pattern:
                    target_files = filtered_by_pattern

            # 연도 필터링 (주어진 경우, 가급적 해당 연도 파일을 찾음)
            if year_str:
                filtered_by_year = [f for f in target_files if year_str in f["name"]]
                if filtered_by_year:
                    target_files = filtered_by_year
                else:
                    logger.info(f"[{self.get_service_name()}] 파일명에 연도({year_str})가 포함된 파일이 없어 전체 파일 중 최신본을 선택합니다.")

            # 3. 최신 파일 선택 및 다운로드
            latest_file = sorted(target_files, key=lambda x: x["name"], reverse=True)[0]
            
            if folder_name:
                content = self.drive_adapter.get_file(latest_file["name"], folder=folder_name)
            else:
                content = self.drive_adapter.download_file(latest_file["id"])
            
            if not content:
                logger.error(f"[{self.get_service_name()}] 파일을 다운로드할 수 없습니다: {latest_file['name']}")
                return []

            # 4. 파싱 및 저장
            result = parser_func(content, **kwargs)
            save_func(result)
            
            # 결과가 리스트가 아닌 단일 객체일 경우 처리
            is_list = isinstance(result, list)
            items_count = len(result) if is_list else 1
            
            logger.info(f"[{self.get_service_name()}] {latest_file['name']} 동기화 완료: {items_count}건")
            return result if is_list else [result]
        except Exception as e:
            logger.error(f"[{self.get_service_name()}] 동기화 중 오류 발생: {e}", exc_info=True)
            return []
