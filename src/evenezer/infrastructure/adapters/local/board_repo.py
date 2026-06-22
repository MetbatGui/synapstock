"""로컬 JSON 파일 기반 Board 저장소 어댑터."""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

from evenezer.domain.models import Board, BoardSyncManifest, Node, Stock
from evenezer.domain.ports import BoardRepositoryPort, BoardSyncManifestRepositoryPort

DEFAULT_ROOT = Path("data/board")


class LocalBoardRepository(BoardRepositoryPort):
    """로컬 파일시스템(JSON)을 기반으로 Board를 저장 및 조회하는 어댑터입니다."""

    def __init__(self, root_dir: Path = DEFAULT_ROOT) -> None:
        """LocalBoardRepository를 초기화합니다.

        Args:
            root_dir: JSON 파일이 저장되는 루트 디렉터리 경로.
        """
        self.root_dir = root_dir
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self._boards_cache = {}  # name -> Board
        self._last_mtimes = {}  # name -> float

    def _path(self, name: str) -> Path:
        """보드 명칭에 대응하는 로컬 JSON 파일 경로를 생성하고 검증합니다.

        경로 Traversal 공격 방지를 위해 생성된 절대 경로가 root_dir 하위에 포함되는지 대조합니다.

        Args:
            name: 보드 파일의 기본 이름 (예: 'virtual_korea').

        Returns:
            검증 완료된 파일 시스템 상의 Path 객체.

        Raises:
            ValueError: 경로 traversal이 감지된 경우.
        """
        base_resolved = self.root_dir.resolve()
        target_path = (base_resolved / f"{name}.json").resolve()

        if not target_path.is_relative_to(base_resolved):
            raise ValueError(f"Access Denied: Path traversal detected for board name '{name}'")

        return target_path

    def load(self, name: str) -> Board:
        """지정된 보드 이름의 JSON 파일을 읽어 Board 도메인 모델로 역직렬화합니다.

        기본형 JSON 포맷 외에도 구형 트리 구조, 레거시 theme_*.json 포맷을
        자동 감지하여 도메인 모델에 호환되도록 마이그레이션하여 로드합니다.

        Args:
            name: 불러올 보드의 고유 식별 명칭.

        Returns:
            마이그레이션이 적용된 Board 도메인 인스턴스.

        Raises:
            FileNotFoundError: 대상 보드 파일이 로컬 디렉터리에 존재하지 않는 경우.
        """
        path = self._path(name)
        if not path.exists():
            raise FileNotFoundError(f"Board '{name}' not found: {path}")

        current_mtime = path.stat().st_mtime
        cached_mtime = self._last_mtimes.get(name, 0.0)

        if name in self._boards_cache and current_mtime == cached_mtime:
            return self._boards_cache[name]

        raw = json.loads(path.read_text(encoding="utf-8"))

        board = None
        # 1. 정석 JSON 형식 (Board 모델 구조) 확인
        if "nodes" in raw:
            board = Board.model_validate(raw)
            board.id = name  # 파일명을 ID로 고정

        # 1-2. 구형 트리 JSON 형식 (Board 내에 "root" 노드가 존재하는 경우)
        elif "root" in raw:
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
            board = Board(id=name, name=board_name, nodes=nodes_dict)

        # 2. 레거시 형식 (theme_*.json) 처리
        else:
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
                        if ":" in co:
                            co_name, co_ticker = co.split(":", 1)
                        else:
                            co_name, co_ticker = co, ""
                        child.stocks.append(Stock(name=co_name.strip(), ticker=co_ticker.strip()))

                    nodes_dict[current_path] = child

                    sub = item.get("sectors") or item.get("categories") or item.get("sub_categories_2")
                    if sub:
                        _walk(sub, current_path, parent_depth + 1)

            if "sectors" in raw:
                _walk(raw["sectors"], b_name, 0)

            board = Board(id=name, name=b_name, nodes=nodes_dict)

        if board:
            self._boards_cache[name] = board
            self._last_mtimes[name] = current_mtime
            return board
        else:
            raise ValueError(f"Failed to parse board data for '{name}'")

    def save(self, board: Board) -> None:
        """Board 인스턴스를 지정된 JSON 파일 경로에 직렬화하여 저장합니다.

        Args:
            board: 저장할 Board 도메인 인스턴스.
        """
        filename = board.id or board.name
        path = self._path(filename)
        path.write_text(
            board.model_dump_json(indent=2, exclude={"id"}, exclude_defaults=True), encoding="utf-8"
        )

        # 캐시 갱신 (Write-through)
        self._boards_cache[filename] = board
        self._last_mtimes[filename] = path.stat().st_mtime

    def list_boards(self) -> list[str]:
        """저장소 디렉터리 내에 저장된 theme_* 또는 virtual_* 형태의 보드 파일 이름 목록을 반환합니다.

        Returns:
            정렬된 보드 식별 명칭(파일명의 stem) 목록.
        """
        return sorted(
            p.stem for p in self.root_dir.glob("*.json")
            if p.name.startswith("theme_") or p.name.startswith("virtual_")
        )

    def delete(self, name: str) -> None:
        """이름에 매칭되는 보드 JSON 파일을 삭제합니다.

        Args:
            name: 삭제할 보드의 식별 명칭.

        Raises:
            FileNotFoundError: 삭제 대상 보드 파일이 없는 경우.
        """
        path = self._path(name)
        if path.exists():
            path.unlink()
            # 캐시 제거
            if name in self._boards_cache:
                del self._boards_cache[name]
            if name in self._last_mtimes:
                del self._last_mtimes[name]
        else:
            raise FileNotFoundError(f"Board '{name}' not found: {path}")


class LocalBoardSyncManifestRepository(BoardSyncManifestRepositoryPort):
    """로컬 JSON 파일을 기반으로 통합 동기화 매니페스트 데이터를 저장하고 조회하는 어댑터입니다."""

    def __init__(self, manifest_path: Path = Path("data/board/board_sync_manifest.json")) -> None:
        """LocalBoardSyncManifestRepository를 초기화합니다.

        Args:
            manifest_path: 매니페스트 JSON 파일이 저장되는 경로.
        """
        self.manifest_path = manifest_path

    def load(self) -> BoardSyncManifest:
        """매니페스트 JSON 파일을 읽어 BoardSyncManifest 도메인 객체로 변환합니다.

        파일이 존재하지 않거나 로드 실패 시 빈 구조의 매니페스트 인스턴스를 반환합니다.

        Returns:
            검증 완료된 BoardSyncManifest 객체.
        """
        if not self.manifest_path.exists():
            return BoardSyncManifest()
        try:
            raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            return BoardSyncManifest.model_validate(raw)
        except Exception as e:
            logger.error(f"[BoardSyncManifestRepository] 매니페스트 로드 중 예외 발생: {e}", exc_info=True)
            return BoardSyncManifest()

    def save(self, manifest: BoardSyncManifest) -> None:
        """BoardSyncManifest 도메인 인스턴스를 JSON 포맷 파일로 직렬화하여 영속화합니다.

        Args:
            manifest: 저장할 BoardSyncManifest 인스턴스.
        """
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(
            manifest.model_dump_json(indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

