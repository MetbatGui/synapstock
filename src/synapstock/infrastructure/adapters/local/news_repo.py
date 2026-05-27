import json
import logging
import os
from pathlib import Path

from synapstock.domain.news.models import NewsBatch
from synapstock.domain.ports import NewsRepositoryPort

logger = logging.getLogger(__name__)

class LocalNewsRepository(NewsRepositoryPort):
    """뉴스 데이터를 로컬 파일 시스템에 JSON 형식으로 저장하는 Repository."""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_file_path(self, date_str: str) -> Path:
        """날짜별 파일 경로를 반환합니다. (예: news_2024-04-23.json)"""
        return self.base_dir / f"news_{date_str}.json"

    def save_batch(self, batch: NewsBatch) -> bool:
        """뉴스 배치를 JSON 파일로 저장합니다."""
        file_path = self._get_file_path(batch.date)
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                # Pydantic 모델을 JSON으로 변환하여 저장
                f.write(batch.model_dump_json(indent=2))
            return True
        except Exception as e:
            logger.error(f"[NewsRepo] 파일 저장 실패 ({batch.date}): {e}")
            return False

    def load_batch(self, date_str: str) -> NewsBatch | None:
        """특정 날짜의 뉴스 배치를 로드합니다."""
        file_path = self._get_file_path(date_str)
        if not file_path.exists():
            return None

        try:
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)
                return NewsBatch(**data)
        except Exception as e:
            logger.error(f"[NewsRepo] 파일 로드 실패 ({date_str}): {e}")
            return None

    def list_available_dates(self) -> list[str]:
        """데이터가 존재하는 모든 날짜 목록을 반환합니다."""
        dates = []
        for f in self.base_dir.glob("news_*.json"):
            if f.name == "news_metadata.json":
                continue
            # news_2024-04-23.json -> 2024-04-23 추출
            date_str = f.stem.replace("news_", "")
            dates.append(date_str)
        return sorted(dates, reverse=True)

    def get_file_mtime(self, date_str: str) -> float:
        """로컬 뉴스 파일의 마지막 수정 시각(POSIX timestamp)을 반환합니다."""
        file_path = self._get_file_path(date_str)
        if not file_path.exists():
            return 0.0
        return file_path.stat().st_mtime

    def get_all_batch_files(self) -> list[Path]:
        """모든 뉴스 배치 파일 경로 목록을 반환합니다. (메타데이터 파일 제외)"""
        return [
            f for f in self.base_dir.glob("news_*.json")
            if f.name != "news_metadata.json"
        ]

    def save_raw_file(self, filename: str, content: bytes, mtime: float | None = None) -> None:
        """파일 내용을 저장하고 선택적으로 수정 시각을 설정합니다."""
        file_path = self.base_dir / filename
        with open(file_path, "wb") as f:
            f.write(content)
        if mtime is not None:
            os.utime(file_path, (mtime, mtime))

    def load_sync_metadata(self) -> dict:
        """동기화 메타데이터를 로드합니다."""
        metadata_path = self.base_dir / "news_metadata.json"
        if not metadata_path.exists():
            return {}
        try:
            with open(metadata_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def save_sync_metadata(self, metadata: dict) -> None:
        """동기화 메타데이터를 저장합니다."""
        metadata_path = self.base_dir / "news_metadata.json"
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)
