"""Stock, Node, Board 도메인 모델 정의."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, model_validator


class Stock(BaseModel):
    """주식 종목 모델.

    Attributes:
        name: 종목명.
        ticker: 종목 코드 (예: '005930').
    """

    name: str
    ticker: str

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

    name: str
    root: Node

    @model_validator(mode="before")
    @classmethod
    def create_root_node(cls, data: Any) -> Any:
        """root가 없을 경우 Board name으로 루트 노드를 자동 생성한다."""
        if isinstance(data, dict) and "root" not in data and "name" in data:
            data["root"] = Node(name=data["name"], depth=0)
        return data

    def __repr__(self) -> str:
        return f"Board({self.name!r})\n{self.root!r}"

    def __str__(self) -> str:
        return self.__repr__()


# 재귀 참조 해소 (Node.nodes: list[Node])
Node.model_rebuild()
