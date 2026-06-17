import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

class LocalCacheManager:
    """로컬 캐시 상태를 관리하는 매니저 클래스.

    데이터 소스(예: Google Drive)의 파일 메타데이터를 로컬 매니페스트에 저장하고
    변경 사항이 있을 때만 업데이트를 허용하도록 돕습니다.
    """

    def __init__(self, manifest_path: str = "data/statistics/cache_manifest.json"):
        """LocalCacheManager를 초기화하고 캐시 매니페스트 파일을 로드합니다.

        Args:
            manifest_path: 캐시 상태 정보를 영속화할 JSON 매니페스트 파일 경로.
        """
        self.manifest_path = Path(manifest_path)
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache = self._load_manifest()

    def _load_manifest(self) -> dict[str, dict[str, Any]]:
        """로컬 파일로부터 캐시 상태 매니페스트 데이터를 로드합니다.

        Returns:
            카테고리 및 파일명을 키로 하고 메타데이터를 값으로 하는 딕셔너리.
            파일이 없거나 손상된 경우 빈 딕셔너리를 반환합니다.
        """
        if not self.manifest_path.exists():
            return {}
        try:
            with open(self.manifest_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"[LocalCacheManager] 매니페스트 로드 실패: {e}")
            return {}

    def _save_manifest(self):
        """현재 인메모리 캐시 상태를 디스크에 영속화합니다."""
        try:
            with open(self.manifest_path, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[LocalCacheManager] 매니페스트 저장 실패: {e}")

    def needs_update(self, category: str, file_name: str, modified_time: str) -> bool:
        """클라우드의 특정 파일이 로컬 캐시 대비 업데이트가 필요한지 여부를 판별합니다.

        Args:
            category: 데이터 카테고리 분류 명칭 (예: 'ceiling').
            file_name: 확인 대상 파일명 (예: 'data.xlsx').
            modified_time: 클라우드 상의 마지막 수정 시각 문자열.

        Returns:
            캐시된 수정 시각과 다를 때 또는 캐시에 존재하지 않을 때 True, 그 외에는 False.
        """
        key = f"{category}:{file_name}"
        cached_info = self.cache.get(key)

        if not cached_info:
            return True

        return cached_info.get("modified_time") != modified_time

    def update_cache_info(self, category: str, file_name: str, modified_time: str, extra: dict | None = None):
        """특정 파일의 동기화 상태 메타데이터를 매니페스트 캐시에 업데이트하고 영속화합니다.

        Args:
            category: 데이터 카테고리 분류 명칭.
            file_name: 대상 파일명.
            modified_time: 새롭게 갱신된 파일 수정 시각 문자열.
            extra: 추가적으로 기록할 임의의 키-값 정보 딕셔너리.
        """
        key = f"{category}:{file_name}"
        self.cache[key] = {
            "modified_time": modified_time,
            "updated_at": Path().stat().st_mtime,
            **(extra or {})
        }
        self._save_manifest()
