from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from enum import Enum
from typing import Any

from pydantic import BaseModel, model_validator


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
    news: list[dict[str, str]] = [] # [{"title": "...", "date": "...", "url": "..."}]

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
    news: list[dict[str, str]] = [] # [{"title": "...", "date": "...", "url": "..."}]

    def find_node(self, name: str) -> Node | None:
        """이름으로 하위 노드를 재귀적으로 검색한다."""
        if self.name == name:
            return self
        for child in self.nodes:
            found = child.find_node(name)
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

    def find_and_add_news(self, ticker: str, news_entry: dict) -> bool:
        """재귀적으로 종목을 찾아 뉴스를 추가한다."""
        for s in self.stocks:
            if s.ticker == ticker:
                if not any(n["url"] == news_entry["url"] for n in s.news):
                    s.news.append(news_entry)
                return True
        for child in self.nodes:
            if child.find_and_add_news(ticker, news_entry):
                return True
        return False

    def find_and_remove_news(self, ticker: str, url: str) -> bool:
        """재귀적으로 종목을 찾아 특정 뉴스를 삭제한다."""
        for s in self.stocks:
            if s.ticker == ticker:
                new_news = [n for n in s.news if n["url"] != url]
                if len(new_news) < len(s.news):
                    s.news = new_news
                    return True
                return False
        for child in self.nodes:
            if child.find_and_remove_news(ticker, url):
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

    id: str | None = None # 파일명 및 고유 식별자
    name: str # 표시 이름
    root: Node

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
