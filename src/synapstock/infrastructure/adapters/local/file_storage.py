import logging
import shutil
from pathlib import Path

from synapstock.domain.ports import StoragePort

logger = logging.getLogger(__name__)


class LocalFileStorageAdapter(StoragePort):
    """로컬 파일 시스템을 위한 StoragePort 구현체."""

    def __init__(self, base_dir: str | Path = "."):
        self.base_dir = Path(base_dir)

    def _get_abs_path(self, path: str) -> Path:
        """상대 경로를 인스턴스 기준의 절대 경로로 변환한다."""
        p = Path(path)
        if p.is_absolute():
            return p
        return self.base_dir / p

    def path_exists(self, path: str, **kwargs) -> bool:
        """경로 존재 여부를 확인한다."""
        return self._get_abs_path(path).exists()

    def ensure_directory(self, path: str, **kwargs) -> bool:
        """디렉토리가 없으면 생성한다."""
        try:
            self._get_abs_path(path).mkdir(parents=True, exist_ok=True)
            return True
        except Exception as e:
            logger.error(f"Failed to create directory {path}: {e}")
            return False

    def get_file(self, path: str, **kwargs) -> bytes | None:
        """파일 내용을 읽어온다."""
        abs_path = self._get_abs_path(path)
        if not abs_path.is_file():
            return None
        try:
            return abs_path.read_bytes()
        except Exception as e:
            logger.error(f"Failed to read file {path}: {e}")
            return None

    def put_file(self, path: str, data: bytes, **kwargs) -> bool:
        """데이터를 파일로 저장한다."""
        abs_path = self._get_abs_path(path)
        try:
            # 부모 디렉토리가 없으면 생성
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_bytes(data)
            return True
        except Exception as e:
            logger.error(f"Failed to write file {path}: {e}")
            return False

    def list_files_in_folder(self, folder_path: str, **kwargs) -> list[dict]:
        """폴더 내 파일 목록을 반환한다."""
        abs_path = self._get_abs_path(folder_path)
        if not abs_path.is_dir():
            return []

        results = []
        for p in abs_path.iterdir():
            if p.is_file():
                results.append(
                    {"id": str(p.relative_to(self.base_dir)) if not p.is_absolute() else str(p), "name": p.name}
                )
        return results

    def download_file(self, filename: str, local_path: str, **kwargs) -> bool:
        """파일을 복사한다 (로컬 어댑터에서는 copy와 유사)."""
        src = self._get_abs_path(filename)
        dest = Path(local_path)

        if not src.exists():
            return False

        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            return True
        except Exception as e:
            logger.error(f"Failed to download(copy) file {filename} to {local_path}: {e}")
            return False
