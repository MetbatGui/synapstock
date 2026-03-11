"""로컬 폴더 구조 기반 마인드맵 어댑터.

폴더 = 노드, .json 파일 = 종목으로 Board 트리를 로컬 파일시스템에 반영한다.

폴더 구조 규약::

    data/folder_mindmap/
    └── {Board이름}/          ← 보드 루트 폴더
        └── {Board이름}/      ← 루트 노드 폴더 (depth=0, Board와 동명)
            └── {노드명}/     ← 자식 노드 폴더 (재귀)
                └── {종목명}.json  ← 종목 파일 {"name": ..., "ticker": ...}
"""

import shutil
from pathlib import Path

from synapstock.domain.models import Board, Node, Stock
from synapstock.domain.ports import MindmapPort

DEFAULT_ROOT = Path("data/folder_mindmap")


class LocalFolderMindmapAdapter(MindmapPort):
    """로컬 폴더 구조를 마인드맵처럼 사용하는 어댑터.

    추후 Miro 어댑터로 교체 시 MindmapPort를 구현하는 MiroMindmapAdapter로 대체된다.

    Attributes:
        root_dir: 보드 폴더들이 저장되는 루트 디렉터리.
    """

    def __init__(self, root_dir: Path = DEFAULT_ROOT) -> None:
        self.root_dir = root_dir
        self.root_dir.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------------
    # MindmapPort 구현
    # -------------------------------------------------------------------------

    def load(self, board_name: str) -> Board:
        """폴더 트리를 재귀 탐색하여 Board를 복원한다.

        Args:
            board_name: 보드 이름 (폴더명).

        Returns:
            복원된 Board 인스턴스.

        Raises:
            FileNotFoundError: 보드 폴더 또는 루트 노드 폴더가 없을 때.
        """
        board_dir = self.root_dir / board_name
        if not board_dir.exists():
            raise FileNotFoundError(f"Board '{board_name}' not found: {board_dir}")

        root_node_dir = board_dir / board_name
        if not root_node_dir.exists():
            raise FileNotFoundError(
                f"Board '{board_name}'의 루트 노드 폴더가 없습니다: {root_node_dir}"
            )

        root = self._load_node(root_node_dir, depth=0)
        return Board(name=board_name, root=root)

    def save(self, board: Board) -> None:
        """Board 트리를 폴더/파일 구조로 직렬화한다.

        기존 보드 폴더를 삭제 후 재생성한다 (덮어쓰기).

        Args:
            board: 저장할 Board 인스턴스.
        """
        board_dir = self.root_dir / board.name
        if board_dir.exists():
            shutil.rmtree(board_dir)

        root_node_dir = board_dir / board.name
        self._save_node(board.root, root_node_dir)

    def list_boards(self) -> list[str]:
        """루트 디렉터리 하위 폴더 이름 목록을 반환한다.

        Returns:
            Board 이름 리스트 (정렬됨).
        """
        return sorted(d.name for d in self.root_dir.iterdir() if d.is_dir())

    # -------------------------------------------------------------------------
    # 내부 헬퍼
    # -------------------------------------------------------------------------

    def _load_node(self, path: Path, depth: int) -> Node:
        """폴더를 재귀 탐색하여 Node를 복원한다.

        Args:
            path: 현재 노드에 해당하는 폴더 경로.
            depth: 현재 노드의 깊이.

        Returns:
            복원된 Node 인스턴스.
        """
        node = Node(name=path.name, depth=depth)
        for item in sorted(path.iterdir()):
            if item.is_dir():
                node.nodes.append(self._load_node(item, depth + 1))
            elif item.suffix == ".json":
                node.stocks.append(
                    Stock.model_validate_json(item.read_text(encoding="utf-8-sig"))
                )
        return node

    def _save_node(self, node: Node, path: Path) -> None:
        """Node를 폴더/파일로 직렬화한다.

        Args:
            node: 저장할 Node 인스턴스.
            path: 이 노드에 해당하는 폴더 경로.
        """
        path.mkdir(parents=True, exist_ok=True)
        for stock in node.stocks:
            (path / f"{stock.name}.json").write_text(
                stock.model_dump_json(indent=2), encoding="utf-8"
            )
        for child in node.nodes:
            self._save_node(child, path / child.name)
