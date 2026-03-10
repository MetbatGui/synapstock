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


# 재귀 참조 해소 (Node.nodes: list[Node])
Node.model_rebuild()
