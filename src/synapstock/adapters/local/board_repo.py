"""로컬 JSON 파일 기반 Board 저장소 어댑터."""

from pathlib import Path

from synapstock.domain.models import Board
from synapstock.domain.ports import BoardRepositoryPort

DEFAULT_ROOT = Path("data/tmp_boards")


class LocalBoardRepository(BoardRepositoryPort):
    """로컬 파일시스템(JSON)을 기반으로 Board를 저장/불러오기한다.

    Attributes:
        root_dir: JSON 파일이 저장되는 루트 디렉터리.
    """

    def __init__(self, root_dir: Path = DEFAULT_ROOT) -> None:
        self.root_dir = root_dir
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        return self.root_dir / f"{name}.json"

    def load(self, name: str) -> Board:
        """name.json 파일을 읽어 Board로 파싱한다.

        Args:
            name: Board 이름.

        Returns:
            파싱된 Board 인스턴스.

        Raises:
            FileNotFoundError: 파일이 존재하지 않을 때.
        """
        path = self._path(name)
        if not path.exists():
            raise FileNotFoundError(f"Board '{name}' not found: {path}")
        return Board.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, board: Board) -> None:
        """Board를 name.json 파일로 저장한다.

        Args:
            board: 저장할 Board 인스턴스.
        """
        self._path(board.name).write_text(
            board.model_dump_json(indent=2), encoding="utf-8"
        )

    def list_boards(self) -> list[str]:
        """루트 디렉터리의 .json 파일 이름 목록을 반환한다.

        Returns:
            Board 이름 리스트 (확장자 제외, 알파벳 정렬).
        """
        return sorted(p.stem for p in self.root_dir.glob("*.json"))
