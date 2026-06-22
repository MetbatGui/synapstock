from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, PrivateAttr, model_validator

from evenezer.domain.events import DomainEvent, NodeAdded, NodeDeleted, StockAddedToBoard, StockDeletedFromBoard
from evenezer.domain.statistics.models import NewListing


class Stock(BaseModel):
    """주식 종목 모델.

    Attributes:
        name: 종목명.
        ticker: 종목 코드 (예: '005930').
        aliases: 이전 사명 또는 기타 별칭 목록.
    """

    name: str
    ticker: str
    aliases: list[str] = Field(default_factory=list)
    reports: list[str] = Field(default_factory=list)
    news: list[dict] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_ticker(self) -> Stock:
        """티커 규격(예: 6자리 숫자/영문 구조)을 자율 검증합니다.

        Returns:
            검증 및 공백 제거 처리가 완료된 자기 자신(Stock) 인스턴스.

        Raises:
            ValueError: 티커가 6자리 숫자가 아니거나 영문/숫자 구조가 아닐 경우.
        """
        self.ticker = self.ticker.strip()
        if self.ticker == "":
            return self
        if not self.ticker.isalnum() or len(self.ticker) != 6:
            raise ValueError(f"유효하지 않은 주식 티커 심볼입니다 (6자리 숫자 혹은 영문이어야 함): {self.ticker}")
        return self

    def matches(self, query: str) -> bool:
        """사명 또는 별칭에 검색어가 부합하는지 도메인 내부에서 스스로 확인합니다.

        Args:
            query: 검색어 문자열.

        Returns:
            종목명 또는 별칭 중 하나라도 검색어를 포함하면 True, 그렇지 않으면 False.
        """
        normalized_query = query.strip().lower()
        if normalized_query in self.name.lower():
            return True
        return any(normalized_query in alias.lower() for alias in self.aliases)

    @property
    def has_valid_ticker(self) -> bool:
        """티커가 유효한 6자리 숫자/영문 구조인지 여부를 반환합니다."""
        ticker_stripped = self.ticker.strip() if self.ticker else ""
        return bool(ticker_stripped and ticker_stripped.isalnum() and len(ticker_stripped) == 6)

    def rename(self, new_name: str) -> None:
        """사명 변경 시 기존 사명을 aliases로 격하하고 새 사명을 적용합니다.

        Args:
            new_name: 새로 변경할 사명.
        """
        if self.name != new_name:
            if self.name not in self.aliases:
                self.aliases.append(self.name)
            self.name = new_name

    def __repr__(self) -> str:
        return f"Stock(name={self.name!r}, ticker={self.ticker!r})"

    def __str__(self) -> str:
        return f"- {self.name} ({self.ticker})"


class Node(BaseModel):
    """마인드맵 노드 모델.

    경로 기반 플랫 모델을 지니며, 자식들을 중첩하여 가지지 않습니다.

    Attributes:
        name: 노드 이름.
        depth: root 노드와의 거리 (root=0).
        parent_path: 부모 노드의 절대 경로.
        stocks: 이 노드에 속한 종목 목록.
    """

    name: str
    depth: int
    parent_path: str | None = None
    stocks: list[Stock] = Field(default_factory=list)

    @property
    def path_parts(self) -> list[str]:
        """노드의 절대 경로를 구성하는 세그먼트 목록을 반환합니다.

        예: parent_path='조선/재료', name='철강' -> ['조선', '재료', '철강']
        """
        full_path = f"{self.parent_path}/{self.name}" if self.parent_path else self.name
        return full_path.split("/")

    def __repr__(self) -> str:
        return f"Node(name={self.name!r}, depth={self.depth}, stock_count={len(self.stocks)})"

    def __str__(self) -> str:
        return f"Node '{self.name}' (depth {self.depth})"

    def add_stock(self, stock: Stock) -> bool:
        """중복 체크 후 종목을 추가합니다. 이미 존재하면 추가하지 않고 True를 반환합니다.

        Args:
            stock: 추가할 Stock 인스턴스.

        Returns:
            성공적으로 추가되었거나 이미 존재하면 True.
        """
        if any(s.ticker == stock.ticker for s in self.stocks):
            return True
        self.stocks.append(stock)
        return True

    def remove_stock(self, ticker: str) -> bool:
        """티커로 종목을 찾아 삭제합니다.

        Args:
            ticker: 삭제할 주식 종목 코드 (6자리).

        Returns:
            종목이 존재하여 삭제 완료했으면 True, 존재하지 않았으면 False.
        """
        orig_len = len(self.stocks)
        self.stocks = [s for s in self.stocks if s.ticker != ticker]
        return len(self.stocks) < orig_len


class Board(BaseModel):
    """마인드맵 보드 모델.

    Board 생성 시 루트 노드(depth=0, Key는 보드명)가 자동으로 생성된다.
    모든 하위 노드는 absolute path 키값을 가진 평탄화된 nodes 딕셔너리로 일원화 관리된다.

    Attributes:
        name: 보드 이름.
        nodes: 경로(Key)별 Node(Value) 매핑 딕셔너리.
    """

    id: str | None = None  # 파일명 및 고유 식별자
    name: str  # 표시 이름
    nodes: dict[str, Node] = Field(default_factory=dict)
    _events: list[DomainEvent] = PrivateAttr(default_factory=list)

    def pull_events(self) -> list[DomainEvent]:
        """수집된 도메인 이벤트를 반환하고 버퍼를 비웁니다.

        Returns:
            수집되었던 도메인 이벤트 객체 리스트.
        """
        events = list(self._events)
        self._events.clear()
        return events

    @property
    def root(self) -> Node:
        """재귀 트리 호환을 위해 루트 노드 객체를 탐색하여 반환합니다."""
        # parent_path가 None인 노드가 루트 노드입니다.
        root_node = next((n for n in self.nodes.values() if n.parent_path is None), None)
        if not root_node:
            # 폴백용 자동 복구
            root_node = Node(name=self.name, depth=0, parent_path=None)
            self.nodes[self.name] = root_node
        return root_node

    @property
    def is_virtual(self) -> bool:
        """virtual_ 접두사 존재 여부를 바탕으로 가상 보드 여부를 판별합니다."""
        target = self.id or self.name
        return target is not None and target.startswith("virtual_")

    @model_validator(mode="before")
    @classmethod
    def create_root_node(cls, data: Any) -> Any:
        """nodes가 없을 경우 Board name으로 루트 노드를 자동 생성한다."""
        if isinstance(data, dict) and "nodes" not in data and "name" in data:
            root_name = data["name"]
            data["nodes"] = {
                root_name: Node(name=root_name, depth=0, parent_path=None)
            }
        return data

    def find_node(self, name: str) -> Node | None:
        """보드 내에서 절대 경로(name)로 노드를 검색합니다.

        Args:
            name: 검색할 노드의 절대 경로.

        Returns:
            검색된 Node 객체. 해당 노드가 없으면 None.
        """
        return self.nodes.get(name)

    def find_stock(self, ticker: str) -> Stock | None:
        """보드 내에서 티커로 종목을 검색합니다.

        Args:
            ticker: 검색할 주식 종목 코드 (6자리).

        Returns:
            검색된 Stock 객체. 해당 종목이 없으면 None.
        """
        for node in self.nodes.values():
            for stock in node.stocks:
                if stock.ticker == ticker:
                    return stock
        return None

    def add_node(self, parent_name: str, node_name: str) -> bool:
        """특정 부모 노드 하위에 새 자식 노드를 추가합니다.

        Args:
            parent_name: 부모 노드의 절대 경로.
            node_name: 추가할 자식 노드의 단순 이름.

        Returns:
            성공적으로 추가되었거나 이미 해당 경로 노드가 존재하면 True. 부모가 존재하지 않으면 False.
        """
        parent = self.find_node(parent_name)
        if not parent:
            return False

        new_path = f"{parent_name}/{node_name}"
        if new_path in self.nodes:
            return True

        self.nodes[new_path] = Node(
            name=node_name,
            depth=parent.depth + 1,
            parent_path=parent_name
        )
        self._events.append(NodeAdded(board_id=self.id or self.name, parent_path=parent_name, node_name=node_name))
        return True

    def add_stock_to_node(self, parent_name: str, stock: Stock) -> bool:
        """특정 노드 하위에 종목을 추가합니다.

        Args:
            parent_name: 종목을 추가할 대상 노드의 절대 경로.
            stock: 추가할 Stock 인스턴스.

        Returns:
            성공적으로 추가되었으면 True, 실패 시(부모 노드가 없는 경우 등) False.
        """
        parent = self.find_node(parent_name)
        if not parent:
            return False
        if parent.add_stock(stock):
            self._events.append(StockAddedToBoard(
                board_id=self.id or self.name,
                parent_path=parent_name,
                ticker=stock.ticker,
                stock_name=stock.name
            ))
            return True
        return False

    def delete_node(self, node_name: str) -> bool:
        """노드를 삭제하고 하위 요소를 부모 노드로 흡수(이동)합니다. (루트 노드 제외)

        Args:
            node_name: 삭제할 대상 노드의 절대 경로.

        Returns:
            성공적으로 노드가 삭제되어 자식 및 종목이 재배치되었으면 True,
            삭제 대상이 없거나 부모 경로가 없는 경우(루트 노드) False.
        """
        node = self.find_node(node_name)
        if not node or node.parent_path is None:
            return False

        parent_path = node.parent_path
        parent_node = self.find_node(parent_path)
        if not parent_node:
            return False

        # 1. 삭제 대상 노드의 종목들을 부모 노드로 이동
        for stock in node.stocks:
            parent_node.add_stock(stock)

        # 2. 하위 자식 노드들의 경로 및 부모 경로 갱신
        child_paths = [p for p in self.nodes.keys() if p.startswith(node_name + "/")]
        child_paths.sort()  # 상위 계층부터 안전하게 재배치하기 위해 정렬

        depth_delta = node.depth - parent_node.depth

        for old_path in child_paths:
            child = self.nodes.pop(old_path)

            # 경로 갱신
            relative_part = old_path[len(node_name):]
            new_path = parent_path + relative_part

            # 부모 경로 갱신
            if child.parent_path == node_name:
                child.parent_path = parent_path
            else:
                assert child.parent_path is not None
                child_rel_parent = child.parent_path[len(node_name):]
                child.parent_path = parent_path + child_rel_parent

            # depth 갱신
            child.depth -= depth_delta

            self.nodes[new_path] = child

        # 3. 본 노드 제거
        self.nodes.pop(node_name, None)
        self._events.append(NodeDeleted(board_id=self.id or self.name, node_path=node_name))
        return True

    def delete_stock(self, ticker: str) -> bool:
        """보드 내에서 특정 종목(티커 기준)을 찾아 삭제합니다.

        Args:
            ticker: 삭제할 주식 종목 코드 (6자리).

        Returns:
            종목이 존재하여 하나 이상의 노드에서 성공적으로 제거되었으면 True, 삭제된 내역이 없으면 False.
        """
        deleted = False
        for node in self.nodes.values():
            if node.remove_stock(ticker):
                deleted = True
        if deleted:
            self._events.append(StockDeletedFromBoard(board_id=self.id or self.name, ticker=ticker))
        return deleted

    def add_report_to_stock(self, ticker: str, report_path: str) -> bool:
        """보드 내에서 특정 종목(티커 기준)을 찾아 리포트 파일 경로를 추가합니다.

        Args:
            ticker: 대상 주식 종목 코드 (6자리).
            report_path: 추가할 리포트 파일의 경로.

        Returns:
            종목을 찾아서 리포트 경로를 추가했으면 True, 종목이 존재하지 않으면 False.
        """
        stock = self.find_stock(ticker)
        if not stock:
            return False
        if report_path not in stock.reports:
            stock.reports.append(report_path)
        return True

    def remove_report_from_stock(self, ticker: str, report_path: str) -> bool:
        """보드 내에서 특정 종목(티커 기준)을 찾아 리포트 경로를 삭제합니다.

        Args:
            ticker: 대상 주식 종목 코드 (6자리).
            report_path: 삭제할 리포트 파일의 경로.

        Returns:
            종목을 찾아 리포트 경로를 성공적으로 제거했으면 True, 종목이 없거나 해당 리포트 경로가 없으면 False.
        """
        stock = self.find_stock(ticker)
        if not stock:
            return False
        if report_path in stock.reports:
            stock.reports.remove(report_path)
            return True
        return False

    def __repr__(self) -> str:
        return f"Board(id={self.id!r}, name={self.name!r}, node_count={len(self.nodes)})"

    def __str__(self) -> str:
        # 기존 트리 형태로 덤프하여 가독성 및 호환을 유지한다.
        root_path = next((path for path, n in self.nodes.items() if n.parent_path is None), None)
        if not root_path:
            return f"Board({self.name!r})\n  (Empty)"

        lines = []
        def _render_tree(path: str, indent: int = 0):
            node = self.nodes[path]
            prefix = "  " * indent
            lines.append(f"{prefix}[D{node.depth}] {node.name}")
            for stock in node.stocks:
                lines.append(f"{prefix}  {stock!s}")

            # 직계 자식 노드 탐색 및 정렬
            children = [p for p, n in self.nodes.items() if n.parent_path == path]
            children.sort()
            for child_path in children:
                _render_tree(child_path, indent + 1)

        _render_tree(root_path, 0)
        return f"Board({self.name!r})\n" + "\n".join(lines)


@dataclass
class ScrapedNews:
    """스크래핑된 뉴스 정보를 담는 값 객체."""

    title: str
    date: str  # YYYY-MM-DD
    url: str


class SearchResultType(Enum):
    """검색 결과의 타입 (종목 또는 섹터/노드)."""

    STOCK = "STOCK"
    SECTOR = "SECTOR"


@dataclass
class SearchResult:
    """검색 결과를 담는 값 객체.

    종목(STOCK) 또는 섹터(SECTOR) 정보를 모두 포함할 수 있음.
    """

    type: SearchResultType
    name: str
    board_name: str
    node_path: list[str]  # ["조선", "재료", ...]
    ticker: str | None = None  # SECTOR일 경우 None


class Report(BaseModel):
    """리포트 도메인 엔티티."""

    filename: str
    stock: str
    title: str
    date: str  # YYYY-MM-DD
    provider: str
    url: str | None = None

    @property
    def stock_nfc(self) -> str:
        return unicodedata.normalize("NFC", self.stock)


class BoardManifestItem(BaseModel):
    """개별 보드의 매니페스트 상태 정보."""

    name: str
    last_modified: float
    deleted: bool = False


class BoardSyncManifest(BaseModel):
    """통합 보드 및 신규 상장주 동기화 상태를 관리하는 매니페스트 도메인 모델."""

    last_updated: str = ""
    boards: dict[str, BoardManifestItem] = Field(default_factory=dict)
    new_listings: dict[str, NewListing] = Field(default_factory=dict)
    processed_event_ids: list[str] = Field(default_factory=list)

    def is_event_processed(self, event_id: str) -> bool:
        """이벤트 ID가 이미 처리 완료되었는지 확인합니다.

        Args:
            event_id: 확인할 이벤트의 고유 ID.

        Returns:
            이미 처리된 이벤트이면 True, 그렇지 않으면 False.
        """
        return event_id in self.processed_event_ids

    def mark_event_processed(self, event_id: str, limit: int = 200) -> None:
        """처리 완료된 이벤트 ID를 기록하고 제한 크기를 초과하면 오래된 항목부터 제거합니다.

        Args:
            event_id: 처리 완료를 기록할 이벤트 고유 ID.
            limit: 보관할 이벤트 ID의 최대 개수 한계치. 기본값은 200.
        """
        if event_id not in self.processed_event_ids:
            self.processed_event_ids.append(event_id)
            if len(self.processed_event_ids) > limit:
                self.processed_event_ids = self.processed_event_ids[-limit:]

    def merge_with(self, remote: BoardSyncManifest) -> BoardSyncManifest:
        """로컬과 원격의 수정 시간(Timestamp) 및 IPO 병합 비즈니스 규칙에 근거하여 두 매니페스트를 통합합니다.

        Args:
            remote: 병합할 대상 원격 매니페스트 객체.

        Returns:
            병합이 완료된 새로운 BoardSyncManifest 인스턴스.
        """
        merged_boards = dict(remote.boards)
        for b_id, l_item in self.boards.items():
            if b_id not in merged_boards:
                merged_boards[b_id] = l_item
            else:
                r_item = merged_boards[b_id]
                if l_item.last_modified > r_item.last_modified:
                    merged_boards[b_id] = l_item

        merged_listings = dict(remote.new_listings)
        for ticker, l_item in self.new_listings.items():
            if ticker not in merged_listings:
                merged_listings[ticker] = l_item
            else:
                r_item = merged_listings[ticker]
                merged_listings[ticker] = l_item.merge_with(r_item)

        # 처리 완료된 이벤트 ID 목록 병합 (합집합 연산 후 최신 200개 유지)
        merged_event_ids = list(set(self.processed_event_ids) | set(remote.processed_event_ids))
        merged_event_ids = merged_event_ids[-200:]

        from datetime import UTC, datetime
        return BoardSyncManifest(
            last_updated=datetime.now(UTC).isoformat(),
            boards=merged_boards,
            new_listings=merged_listings,
            processed_event_ids=merged_event_ids,
        )

    def update_board(self, board_id: str, name: str, deleted: bool = False) -> None:
        """보드가 생성, 수정, 삭제되었을 때 매니페스트 상의 최종 수정 이력을 기록합니다.

        Args:
            board_id: 매니페스트에 등록/수정할 보드의 ID.
            name: 보드의 한글/영문 표시 명칭.
            deleted: 해당 보드가 삭제 상태(Soft delete)인지 여부. 기본값은 False.
        """
        from datetime import UTC, datetime
        self.boards[board_id] = BoardManifestItem(
            name=name,
            last_modified=datetime.now(UTC).timestamp(),
            deleted=deleted
        )
        self.last_updated = datetime.now(UTC).isoformat()
