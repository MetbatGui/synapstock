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
        self.manifest_path = Path(manifest_path)
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache = self._load_manifest()

    def _load_manifest(self) -> dict[str, dict[str, Any]]:
        if not self.manifest_path.exists():
            return {}
        try:
            with open(self.manifest_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"[LocalCacheManager] 매니페스트 로드 실패: {e}")
            return {}

    def _save_manifest(self):
        try:
            with open(self.manifest_path, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[LocalCacheManager] 매니페스트 저장 실패: {e}")

    def needs_update(self, category: str, file_name: str, modified_time: str) -> bool:
        """파일이 업데이트되었거나 캐시에 없는지 확인합니다."""
        key = f"{category}:{file_name}"
        cached_info = self.cache.get(key)
        
        if not cached_info:
            return True
        
        return cached_info.get("modified_time") != modified_time

    def update_cache_info(self, category: str, file_name: str, modified_time: str, extra: dict | None = None):
        """캐시 메타데이터를 업데이트합니다."""
        key = f"{category}:{file_name}"
        self.cache[key] = {
            "modified_time": modified_time,
            "updated_at": Path().stat().st_mtime,
            **(extra or {})
        }
        self._save_manifest()
