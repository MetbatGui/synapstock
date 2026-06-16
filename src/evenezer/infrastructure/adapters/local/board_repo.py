"""로컬 JSON 파일 기반 Board 저장소 어댑터."""

import json
from pathlib import Path

from evenezer.domain.models import Board, Node, Stock, BoardSyncManifest
from evenezer.domain.ports import BoardRepositoryPort, BoardSyncManifestRepositoryPort


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
        """보드 파일명을 기준으로 저장소 디렉터리 하위 경로를 생성한다.
        경로 순회(Path Traversal) 공격 방지를 위해 root_dir 내에 위치하는지 검증한다.
        """
        base_resolved = self.root_dir.resolve()
        target_path = (base_resolved / f"{name}.json").resolve()
        
        if not target_path.is_relative_to(base_resolved):
            raise ValueError(f"Access Denied: Path traversal detected for board name '{name}'")
            
        return target_path

    def load(self, name: str) -> Board:
        """name.json 파일을 읽어 Board로 파싱한다. 테마별 JSON 구조를 지원한다."""
        path = self._path(name)
        if not path.exists():
            raise FileNotFoundError(f"Board '{name}' not found: {path}")

        raw = json.loads(path.read_text(encoding="utf-8"))

        # 1. 정석 JSON 형식 (Board 모델 구조) 확인
        if "nodes" in raw:
            board = Board.model_validate(raw)
            board.id = name  # 파일명을 ID로 고정
            return board

        # 1-2. 구형 트리 JSON 형식 (Board 내에 "root" 노드가 존재하는 경우)
        if "root" in raw:
            board_name = raw.get("name", name)
            root_raw = raw["root"]
            nodes_dict = {}

            def _migrate_node(node_raw: dict, parent_path: str | None = None):
                node_name = node_raw["name"]
                depth = node_raw["depth"]
                current_path = f"{parent_path}/{node_name}" if parent_path else node_name

                stocks = []
                for s in node_raw.get("stocks", []):
                    stocks.append(Stock(
                        name=s["name"],
                        ticker=s["ticker"],
                        aliases=s.get("aliases", []),
                        reports=s.get("reports", []),
                        news=s.get("news", [])
                    ))

                nodes_dict[current_path] = Node(
                    name=node_name,
                    depth=depth,
                    parent_path=parent_path,
                    stocks=stocks
                )

                for child_raw in node_raw.get("nodes", []):
                    _migrate_node(child_raw, current_path)

            _migrate_node(root_raw, None)
            return Board(id=name, name=board_name, nodes=nodes_dict)

        # 2. 레거시 형식 (theme_*.json) 처리
        b_name = raw.get("theme", name)
        nodes_dict = {}
        nodes_dict[b_name] = Node(name=b_name, depth=0, parent_path=None)

        def _walk(items, parent_path: str, parent_depth: int):
            for item in items:
                n_name = item.get("sector_name") or item.get("sub_category_1") or item.get("name")
                if not n_name:
                    continue

                current_path = f"{parent_path}/{n_name}"
                child = Node(name=n_name, depth=parent_depth + 1, parent_path=parent_path, stocks=[])
                
                for co in item.get("companies", []):
                    child.stocks.append(Stock(name=co, ticker=""))

                nodes_dict[current_path] = child

                sub = item.get("sectors") or item.get("categories") or item.get("sub_categories_2")
                if sub:
                    _walk(sub, current_path, parent_depth + 1)

        if "sectors" in raw:
            _walk(raw["sectors"], b_name, 0)

        return Board(id=name, name=b_name, nodes=nodes_dict)

    def save(self, board: Board) -> None:
        """Board를 id.json 파일로 저장한다. id가 없으면 name을 시도한다."""
        filename = board.id or board.name
        self._path(filename).write_text(
            board.model_dump_json(indent=2, exclude={"id"}, exclude_defaults=True), encoding="utf-8"
        )

    def list_boards(self) -> list[str]:
        """루트 디렉터리의 theme_* 또는 virtual_* 형식의 .json 파일 이름 목록을 반환한다."""
        return sorted(
            p.stem for p in self.root_dir.glob("*.json")
            if p.name.startswith("theme_") or p.name.startswith("virtual_")
        )

    def delete(self, name: str) -> None:
        """이름에 해당하는 Board 파일을 삭제한다."""
        path = self._path(name)
        if path.exists():
            path.unlink()
        else:
            raise FileNotFoundError(f"Board '{name}' not found: {path}")


class LocalBoardSyncManifestRepository(BoardSyncManifestRepositoryPort):
    """로컬 JSON 파일을 기반으로 통합 매니페스트를 저장하고 조회하는 어댑터."""

    def __init__(self, manifest_path: Path = Path("data/board/board_sync_manifest.json")) -> None:
        self.manifest_path = manifest_path

    def load(self) -> BoardSyncManifest:
        if not self.manifest_path.exists():
            return BoardSyncManifest()
        try:
            raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            return BoardSyncManifest.model_validate(raw)
        except Exception as e:
            logger.error(f"[BoardSyncManifestRepository] 매니페스트 로드 중 예외 발생: {e}", exc_info=True)
            return BoardSyncManifest()

    def save(self, manifest: BoardSyncManifest) -> None:
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(
            manifest.model_dump_json(indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

