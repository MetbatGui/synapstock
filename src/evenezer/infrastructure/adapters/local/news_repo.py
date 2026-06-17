import json
import logging
import os
from pathlib import Path

from evenezer.domain.news.models import NewsBatch
from evenezer.domain.ports import NewsRepositoryPort

logger = logging.getLogger(__name__)

class LocalNewsRepository(NewsRepositoryPort):
    """뉴스 데이터를 로컬 파일 시스템에 JSON 형식으로 저장하는 Repository."""

    def __init__(self, base_dir: Path):
        """LocalNewsRepository를 초기화하고 저장 디렉토리를 보장합니다.

        Args:
            base_dir: 뉴스 JSON 파일이 저장되는 기본 디렉토리 경로.
        """
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_file_path(self, date_str: str) -> Path:
        """날짜별 뉴스 JSON 파일의 경로를 헬퍼 메서드로 반환합니다.

        Args:
            date_str: 대상 날짜 문자열 (예: '2024-04-23').

        Returns:
            해당 날짜 파일의 Path 객체.
        """
        return self.base_dir / f"news_{date_str}.json"

    def save_batch(self, batch: NewsBatch) -> bool:
        """뉴스 배치 데이터를 JSON 파일로 직렬화하여 영속화합니다.

        Args:
            batch: 저장할 NewsBatch 도메인 모델 인스턴스.

        Returns:
            성공 시 True, 실패 시 False.
        """
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
        """특정 날짜의 뉴스 배치를 로드하여 NewsBatch 모델로 역직렬화합니다.

        Args:
            date_str: 로드할 뉴스 데이터의 날짜 문자열.

        Returns:
            복원된 NewsBatch 도메인 인스턴스, 파일이 존재하지 않거나 에러 발생 시 None.
        """
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
        """로컬 저장소에 뉴스 배치 데이터가 존재하는 날짜 목록을 역순으로 조회합니다.

        Returns:
            날짜 문자열('YYYY-MM-DD') 목록.
        """
        dates = []
        for f in self.base_dir.glob("news_*.json"):
            if f.name == "news_metadata.json":
                continue
            # news_2024-04-23.json -> 2024-04-23 추출
            date_str = f.stem.replace("news_", "")
            dates.append(date_str)
        return sorted(dates, reverse=True)

    def get_file_mtime(self, date_str: str) -> float:
        """지정된 날짜의 뉴스 파일의 마지막 수정 시각(POSIX timestamp)을 반환합니다.

        Args:
            date_str: 조회 대상 날짜 문자열.

        Returns:
            마지막 수정 시각을 나타내는 float 값. 파일이 없을 경우 0.0.
        """
        file_path = self._get_file_path(date_str)
        if not file_path.exists():
            return 0.0
        return file_path.stat().st_mtime

    def get_all_batch_files(self) -> list[Path]:
        """메타데이터 파일을 제외한 모든 뉴스 배치 JSON 파일의 경로 목록을 반환합니다.

        Returns:
            로컬에 영속화된 모든 뉴스 파일의 Path 객체 목록.
        """
        return [
            f for f in self.base_dir.glob("news_*.json")
            if f.name != "news_metadata.json"
        ]

    def save_raw_file(self, filename: str, content: bytes, mtime: float | None = None) -> None:
        """임의의 바이너리 데이터를 파일로 저장하고 선택적으로 파일 수정 시각을 설정합니다.

        Args:
            filename: 저장할 파일 이름.
            content: 파일에 기록할 바이너리 내용.
            mtime: 설정할 수정 시각(timestamp). None일 경우 현재 시각으로 설정됩니다.
        """
        file_path = self.base_dir / filename
        with open(file_path, "wb") as f:
            f.write(content)
        if mtime is not None:
            os.utime(file_path, (mtime, mtime))

    def load_sync_metadata(self) -> dict:
        """클라우드와의 동기화 상태 메타데이터를 파일에서 로드합니다.

        Returns:
            동기화 메타데이터를 나타내는 dict 객체. 파일이 없거나 에러 시 빈 dict.
        """
        metadata_path = self.base_dir / "news_metadata.json"
        if not metadata_path.exists():
            return {}
        try:
            with open(metadata_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def save_sync_metadata(self, metadata: dict) -> None:
        """동기화 상태 메타데이터를 파일로 영속화합니다.

        Args:
            metadata: 저장할 메타데이터 딕셔너리.
        """
        metadata_path = self.base_dir / "news_metadata.json"
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)
