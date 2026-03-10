"""Stock, Node 도메인 모델 정의."""

from __future__ import annotations

from pydantic import BaseModel


class Stock(BaseModel):
    """주식 종목 모델.

    Attributes:
        name: 종목명.
        ticker: 종목 코드 (예: '005930').
    """

    name: str
    ticker: str


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