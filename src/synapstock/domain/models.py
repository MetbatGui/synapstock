from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator
from synapstock.domain.statistics.models import NewListing



class Stock(BaseModel):
    """주식 종목 모델.

    Attributes:
        name: 종목명.
        ticker: 종목 코드 (예: '005930').
        aliases: 이전 사명 또는 기타 별칭 목록.
    """

    name: str
    ticker: str
    aliases: list[str] = []
    reports: list[str] = []
    news: list[dict] = []

    @model_validator(mode="after")
    def validate_ticker(self) -> Stock:
        """티커 규격(예: 6자리 숫자/영문 구조)을 자율 검증합니다."""
        self.ticker = self.ticker.strip()
        if not self.ticker.isalnum() or len(self.ticker) != 6:
            raise ValueError(f"유효하지 않은 주식 티커 심볼입니다 (6자리 숫자 혹은 영문이어야 함): {self.ticker}")
        return self

    def matches(self, query: str) -> bool:
        """사명 또는 별칭에 검색어가 부합하는지 도메인 내부에서 스스로 확인합니다."""
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
        """사명 변경 시 기존 사명을 aliases로 격하하고 새 사명을 적용합니다."""
        if self.name != new_name:
            if self.name not in self.aliases:
                self.aliases.append(self.name)
            self.name = new_name

    def __repr__(self) -> str:
        return f"- {self.name} ({self.ticker})"


class Node(BaseModel):
    """마인드맵 노드 모델.

    재귀적 트리 구조를 가지며, depth는 부모 노드에서 계산 후 주입된다.

    Attributes:
        name: 노드 이름.
        depth: root 노드와의 거리 (root=0).
        nodes: 자식 노드 목록.
        stocks: 이 노드에 속한 종목 목록.
    """

    name: str
    depth: int
    nodes: list[Node] = []
    stocks: list[Stock] = []

    def find_node(self, name: str) -> Node | None:
        """이름으로 하위 노드를 재귀적으로 검색한다."""
        if self.name == name:
            return self
        for child in self.nodes:
            found = child.find_node(name)
            if found:
                return found
        return None

    def find_stock(self, ticker: str) -> Stock | None:
        """티커로 하위 종목을 재귀적으로 검색한다."""
        for stock in self.stocks:
            if stock.ticker == ticker:
                return stock
        for child in self.nodes:
            found = child.find_stock(ticker)
            if found:
                return found
        return None

    def add_stock(self, stock: Stock) -> bool:
        """중복 체크 후 종목을 추가한다. 이미 존재하면 True(성공)를 반환한다."""
        if any(s.ticker == stock.ticker for s in self.stocks):
            return True
        self.stocks.append(stock)
        return True

    def remove_stock(self, ticker: str) -> bool:
        """티커로 종목을 찾아 삭제한다."""
        orig_len = len(self.stocks)
        self.stocks = [s for s in self.stocks if s.ticker != ticker]
        return len(self.stocks) < orig_len

    def find_and_remove_stock(self, ticker: str) -> bool:
        """재귀적으로 종목을 찾아 삭제한다."""
        if self.remove_stock(ticker):
            return True
        for child in self.nodes:
            if child.find_and_remove_stock(ticker):
                return True
        return False



    def find_and_add_report(self, ticker: str, report_path: str) -> bool:
        """재귀적으로 종목을 찾아 리포트 경로를 추가한다."""
        for s in self.stocks:
            if s.ticker == ticker:
                if report_path not in s.reports:
                    s.reports.append(report_path)
                return True
        for child in self.nodes:
            if child.find_and_add_report(ticker, report_path):
                return True
        return False

    def find_and_remove_report(self, ticker: str, report_path: str) -> bool:
        """재귀적으로 종목을 찾아 리포트 경로를 삭제한다."""
        for s in self.stocks:
            if s.ticker == ticker:
                if report_path in s.reports:
                    s.reports.remove(report_path)
                    return True
                return False
        for child in self.nodes:
            if child.find_and_remove_report(ticker, report_path):
                return True
        return False

    def add_child(self, name: str) -> Node:
        """자식 노드를 생성하여 추가하고 반환한다.

        Args:
            name: 자식 노드의 이름.

        Returns:
            생성된 자식 Node 인스턴스.
        """
        child = Node(name=name, depth=self.depth + 1)
        self.nodes.append(child)
        return child

    def remove_child(self, name: str, absorb: bool = True) -> None:
        """자식 노드를 삭제한다.

        Args:
            name: 삭제할 자식 노드의 이름.
            absorb: True일 경우 삭제되는 노드의 자식들을 현재 노드(부모)로 흡수한다.
        """
        target = next((n for n in self.nodes if n.name == name), None)
        if not target:
            return

        if absorb:
            # 1. 자식 노드들을 현재 노드로 이동 및 depth 갱신
            for child_node in target.nodes:
                child_node._update_depth_recursive(self.depth + 1)
                self.nodes.append(child_node)
            # 2. 종목들을 현재 노드(부모)로 이동
            self.stocks.extend(target.stocks)

        self.nodes.remove(target)

    def _update_depth_recursive(self, new_depth: int) -> None:
        """노드와 그 하위 트리 전체의 depth를 재귀적으로 갱신한다."""
        self.depth = new_depth
        for child in self.nodes:
            child._update_depth_recursive(new_depth + 1)

    def _format(self, indent: int = 0) -> str:
        """재귀적으로 트리 문자열을 구성한다."""
        prefix = "  " * indent
        lines = [f"{prefix}[D{self.depth}] {self.name}"]
        for stock in self.stocks:
            lines.append(f"{prefix}  {stock!r}")
        for child in self.nodes:
            lines.append(child._format(indent + 1))
        return "\n".join(lines)

    def __repr__(self) -> str:
        return self._format()

    def __str__(self) -> str:
        return self._format()


class Board(BaseModel):
    """마인드맵 보드 모델.

    Board 생성 시 루트 노드(depth=0)가 자동으로 생성된다.

    Attributes:
        name: 보드 이름.
        root: 자동 생성된 루트 노드 (depth=0, name=보드명).
    """

    id: str | None = None  # 파일명 및 고유 식별자
    name: str  # 표시 이름
    root: Node

    @property
    def is_virtual(self) -> bool:
        """virtual_ 접두사 존재 여부를 바탕으로 가상 보드 여부를 판별합니다."""
        target = self.id or self.name
        return target is not None and target.startswith("virtual_")


    @model_validator(mode="before")
    @classmethod
    def create_root_node(cls, data: Any) -> Any:
        """root가 없을 경우 Board name으로 루트 노드를 자동 생성한다."""
        if isinstance(data, dict) and "root" not in data and "name" in data:
            data["root"] = Node(name=data["name"], depth=0)
        return data

    def find_node(self, name: str) -> Node | None:
        """보드 내에서 이름으로 노드를 검색한다."""
        return self.root.find_node(name)

    def find_stock(self, ticker: str) -> Stock | None:
        """보드 내에서 티커로 종목을 검색한다."""
        return self.root.find_stock(ticker)

    def add_node(self, parent_name: str, node_name: str) -> bool:
        """특정 노드 하위에 새 노드를 추가한다."""
        parent = self.find_node(parent_name)
        if not parent:
            return False
        if any(n.name == node_name for n in parent.nodes):
            return True
        parent.add_child(node_name)
        return True

    def add_stock_to_node(self, parent_name: str, stock: Stock) -> bool:
        """특정 노드 하위에 종목을 추가한다."""
        parent = self.find_node(parent_name)
        if not parent:
            return False
        return parent.add_stock(stock)

    def delete_node(self, node_name: str) -> bool:
        """노드를 삭제하고 하위 요소를 부모로 흡수한다. (루트 제외)"""
        if self.root.name == node_name:
            return False

        def find_and_remove(parent: Node, target_name: str) -> bool:
            for i, child in enumerate(parent.nodes):
                if child.name == target_name:
                    parent.remove_child(target_name, absorb=True)
                    return True
                if find_and_remove(child, target_name):
                    return True
            return False

        return find_and_remove(self.root, node_name)

    def delete_stock(self, ticker: str) -> bool:
        """보드 내에서 특정 종목(티커 기준)을 재귀적으로 찾아 삭제합니다."""
        return self.root.find_and_remove_stock(ticker)

    def add_report_to_stock(self, ticker: str, report_path: str) -> bool:
        """보드 내에서 특정 종목(티커 기준)을 재귀적으로 찾아 리포트 경로를 추가합니다."""
        return self.root.find_and_add_report(ticker, report_path)

    def remove_report_from_stock(self, ticker: str, report_path: str) -> bool:
        """보드 내에서 특정 종목(티커 기준)을 재귀적으로 찾아 리포트 경로를 삭제합니다."""
        return self.root.find_and_remove_report(ticker, report_path)

    def __repr__(self) -> str:
        return f"Board({self.name!r})\n{self.root!r}"

    def __str__(self) -> str:
        return self.__repr__()


# 재귀 참조 해소 (Node.nodes: list[Node])
Node.model_rebuild()


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

    def merge_with(self, remote: BoardSyncManifest) -> BoardSyncManifest:
        """로컬과 원격의 수정 시간(Timestamp) 및 IPO 병합 비즈니스 규칙에 근거하여 두 매니페스트를 통합합니다."""
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

        from datetime import datetime, UTC
        return BoardSyncManifest(
            last_updated=datetime.now(UTC).isoformat(),
            boards=merged_boards,
            new_listings=merged_listings,
        )

    def update_board(self, board_id: str, name: str, deleted: bool = False) -> None:
        """보드가 생성, 수정, 삭제되었을 때 매니페스트 상의 최종 수정 이력을 기록합니다."""
        from datetime import datetime, UTC
        self.boards[board_id] = BoardManifestItem(
            name=name,
            last_modified=datetime.now(UTC).timestamp(),
            deleted=deleted
        )
        self.last_updated = datetime.now(UTC).isoformat()

