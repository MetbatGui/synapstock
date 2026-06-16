import uuid
from dataclasses import dataclass, field, asdict
from typing import Any

@dataclass(frozen=True)
class DomainEvent:
    """모든 도메인 이벤트의 기본 클래스."""
    event_id: str = field(init=False)

    def __post_init__(self) -> None:
        # frozen=True 구조이므로 object.__setattr__을 통해 안전하게 초기화
        object.__setattr__(self, "event_id", str(uuid.uuid4()))

    def to_dict(self) -> dict[str, Any]:
        """도메인 이벤트를 역직렬화 가능한 dict 형식으로 변환합니다."""
        d = asdict(self)
        event_id = d.pop("event_id", None)
        return {
            "event_id": event_id,
            "event_class": self.__class__.__name__,
            "data": d
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DomainEvent":
        """직렬화된 dict 데이터로부터 올바른 도메인 이벤트 인스턴스를 복원합니다."""
        event_class_name = data.get("event_class")
        event_id = data.get("event_id")
        event_data = data.get("data", {}).copy()
        
        target_cls = cls
        if cls == DomainEvent and event_class_name:
            import synapstock.domain.events as ev_module
            target_cls = getattr(ev_module, event_class_name, cls)
        
        # 1. 생성자 필드들을 활용하여 복원 (event_id는 init=False 이므로 생성자 필드에서 분리됨)
        inst = target_cls(**event_data)
        
        # 2. 저장되어 있던 고유 event_id로 최종 복원
        if event_id:
            object.__setattr__(inst, "event_id", event_id)
            
        return inst

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
