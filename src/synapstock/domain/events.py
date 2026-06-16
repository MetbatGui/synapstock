from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class DomainEvent:
    """모든 도메인 이벤트의 기본 클래스."""
    pass

@dataclass(frozen=True)
class BoardCreated(DomainEvent):
    board_id: str
    name: str

@dataclass(frozen=True)
class BoardDeleted(DomainEvent):
    board_id: str

@dataclass(frozen=True)
class NodeAdded(DomainEvent):
    board_id: str
    parent_path: str
    node_name: str

@dataclass(frozen=True)
class NodeDeleted(DomainEvent):
    board_id: str
    node_path: str

@dataclass(frozen=True)
class StockAddedToBoard(DomainEvent):
    board_id: str
    parent_path: str
    ticker: str
    stock_name: str

@dataclass(frozen=True)
class StockDeletedFromBoard(DomainEvent):
    board_id: str
    ticker: str

@dataclass(frozen=True)
class BatchStocksDeletedFromBoard(DomainEvent):
    board_id: str
    tickers: list[str]
