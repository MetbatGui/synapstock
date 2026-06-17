import asyncio
import logging
import shutil
from pathlib import Path

from evenezer.domain.ports import StoragePort

logger = logging.getLogger(__name__)


class LocalFileStorageAdapter(StoragePort):
    """로컬 파일 시스템을 위한 StoragePort 구현체."""

    def __init__(self, base_dir: str | Path = "."):
        """LocalFileStorageAdapter를 초기화합니다.

        Args:
            base_dir: 기준 디렉토리 경로. 파일 탐색의 베이스가 됩니다.
        """
        self.base_dir = Path(base_dir)

    def _get_abs_path(self, path: str) -> Path:
        """상대 경로를 인스턴스 기준의 절대 경로로 변환하고 검증합니다.

        경로 순회(Path Traversal) 공격 방지를 위해 base_dir 내에 위치하는지 검증합니다.

        Args:
            path: 변환 및 검사할 파일 경로.

        Returns:
            검증 완료된 절대 경로 Path 객체.

        Raises:
            ValueError: 경로 traversal이 감지된 경우.
        """
        p = Path(path)
        base_resolved = self.base_dir.resolve()

        if p.is_absolute():
            resolved_path = p.resolve()
        else:
            resolved_path = (base_resolved / p).resolve()

        if not resolved_path.is_relative_to(base_resolved):
            raise ValueError(f"Access Denied: Path traversal detected for path '{path}'")

        return resolved_path

    async def path_exists(self, path: str, **kwargs) -> bool:
        """경로 상에 파일 또는 디렉토리가 존재하는지 여부를 확인합니다.

        Args:
            path: 검사할 파일 상대 경로.

        Returns:
            존재할 경우 True, 그렇지 않으면 False.
        """
        return await asyncio.to_thread(self._get_abs_path(path).exists)

    async def ensure_directory(self, path: str, **kwargs) -> bool:
        """디렉토리가 없으면 상위 계층을 포함하여 생성합니다.

        Args:
            path: 생성할 디렉토리 경로.

        Returns:
            생성 성공 시 True, 실패 시 False.
        """
        def _ensure():
            try:
                self._get_abs_path(path).mkdir(parents=True, exist_ok=True)
                return True
            except Exception as e:
                logger.error(f"Failed to create directory {path}: {e}")
                return False
        return await asyncio.to_thread(_ensure)

    async def get_file(self, path: str, **kwargs) -> bytes | None:
        """파일 전체 내용을 바이너리 데이터로 읽어옵니다.

        Args:
            path: 읽어올 파일 상대 경로.

        Returns:
            파일 바이너리 데이터, 대상이 파일이 아니거나 로드 실패 시 None.
        """
        abs_path = self._get_abs_path(path)
        if not await asyncio.to_thread(abs_path.is_file):
            return None
        try:
            return await asyncio.to_thread(abs_path.read_bytes)
        except Exception as e:
            logger.error(f"Failed to read file {path}: {e}")
            return None

    async def put_file(self, path: str, data: bytes, **kwargs) -> bool:
        """지정된 바이너리 데이터를 파일로 작성합니다. 상위 디렉토리가 없으면 함께 생성합니다.

        원자적 쓰기(Atomic Write) 방식으로 데이터를 임시 파일에 기록한 뒤
        기존 대상 파일에 안전하게 대체하여 파일 데이터의 손상을 원천 예방합니다.

        Args:
            path: 데이터를 작성할 파일 경로.
            data: 기록할 바이너리 바이트 데이터.

        Returns:
            파일 작성 성공 시 True, 실패 시 False.
        """
        abs_path = self._get_abs_path(path)
        def _put():
            import os
            import tempfile
            try:
                # 부모 디렉토리가 없으면 생성
                abs_path.parent.mkdir(parents=True, exist_ok=True)
                # 동일 디렉토리 내에 임시 파일 작성
                with tempfile.NamedTemporaryFile(dir=abs_path.parent, delete=False) as tmp_file:
                    tmp_file.write(data)
                    tmp_path = Path(tmp_file.name)
                try:
                    # 원자적으로 덮어쓰기 대체
                    os.replace(tmp_path, abs_path)
                    return True
                except Exception:
                    if tmp_path.exists():
                        tmp_path.unlink()
                    raise
            except Exception as e:
                logger.error(f"Failed to write file {path}: {e}")
                return False
        return await asyncio.to_thread(_put)

    async def list_files_in_folder(self, folder_path: str, **kwargs) -> list[dict]:
        """지정된 폴더 하위에 존재하는 직계 파일 목록을 가져옵니다.

        Args:
            folder_path: 대상 폴더 경로.

        Returns:
            각 파일의 id 및 name 정보를 담은 딕셔너리 목록.
        """
        abs_path = self._get_abs_path(folder_path)
        if not await asyncio.to_thread(abs_path.is_dir):
            return []

        def _list():
            results = []
            for p in abs_path.iterdir():
                if p.is_file():
                    results.append(
                        {"id": str(p.relative_to(self.base_dir)) if not p.is_absolute() else str(p), "name": p.name}
                    )
            return results
        return await asyncio.to_thread(_list)

    async def download_file(self, filename: str, local_path: str, **kwargs) -> bool:
        """어댑터 내부 경로의 파일을 특정 로컬 경로로 복사하여 전달합니다.

        Args:
            filename: 원본 파일 상대 경로.
            local_path: 복사될 대상 로컬 파일 시스템 경로.

        Returns:
            복사 성공 시 True, 실패 시 False.
        """
        src = self._get_abs_path(filename)
        dest = Path(local_path)

        if not await asyncio.to_thread(src.exists):
            return False

        def _copy():
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                return True
            except Exception as e:
                logger.error(f"Failed to download(copy) file {filename} to {local_path}: {e}")
                return False
        return await asyncio.to_thread(_copy)
