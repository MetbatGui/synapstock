"""로컬 JSON 파일 기반 Board 저장소 어댑터."""

import json
from pathlib import Path

from synapstock.domain.models import Board, Node, Stock
from synapstock.domain.ports import BoardRepositoryPort

DEFAULT_ROOT = Path("data/board")


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
        """name.json 파일을 읽어 Board로 파싱한다. 테마별 JSON 구조를 지원한다."""
        path = self._path(name)
        if not path.exists():
            raise FileNotFoundError(f"Board '{name}' not found: {path}")

        raw = json.loads(path.read_text(encoding="utf-8"))

        # 1. 정석 JSON 형식 (Board 모델 구조) 확인
        if "root" in raw:
            board = Board.model_validate(raw)
            board.id = name # 파일명을 ID로 고정
            return board

        # 2. 레거시 형식 (theme_*.json) 처리
        b_name = raw.get("theme", name)
        root = Node(name=b_name, depth=0)

        def _walk(items, parent):
            for item in items:
                n_name = item.get("sector_name") or item.get("sub_category_1") or item.get("name")
                if not n_name:
                    continue

                child = parent.add_child(n_name)
                for co in item.get("companies", []):
                    child.stocks.append(Stock(name=co, ticker=""))

                sub = item.get("sectors") or item.get("categories") or item.get("sub_categories_2")
                if sub:
                    _walk(sub, child)

        if "sectors" in raw:
            _walk(raw["sectors"], root)

        return Board(id=name, name=b_name, root=root)

    def save(self, board: Board) -> None:
        """Board를 id.json 파일로 저장한다. id가 없으면 name을 시도한다."""
        filename = board.id or board.name
        self._path(filename).write_text(
            board.model_dump_json(indent=2, exclude={'id'}, exclude_defaults=True), encoding="utf-8"
        )

    def list_boards(self) -> list[str]:
        """루트 디렉터리의 .json 파일 이름 목록을 반환한다."""
        return sorted(p.stem for p in self.root_dir.glob("*.json"))
