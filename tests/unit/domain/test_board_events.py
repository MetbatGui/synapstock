import pytest
from evenezer.domain.models import Board, Stock
from evenezer.domain.events import NodeAdded, NodeDeleted, StockAddedToBoard, StockDeletedFromBoard

@pytest.mark.unit
def test_board_events_collection():
    """Board 상태 변경 행위 시 알맞은 이벤트가 수집되고 pull_events로 소멸되는지 검증."""
    board = Board(id="test_board", name="테스트보드")
    
    # 1. 초기 이벤트 버퍼는 비어있어야 함
    assert len(board.pull_events()) == 0
    
    # 2. 노드 추가
    assert board.add_node("테스트보드", "하위노드") is True
    events = board.pull_events()
    assert len(events) == 1
    assert isinstance(events[0], NodeAdded)
    assert events[0].board_id == "test_board"
    assert events[0].parent_path == "테스트보드"
    assert events[0].node_name == "하위노드"
    
    # pull_events 이후에는 비워져야 함
    assert len(board.pull_events()) == 0
    
    # 3. 종목 추가
    stock = Stock(name="삼성전자", ticker="005930")
    assert board.add_stock_to_node("테스트보드/하위노드", stock) is True
    events = board.pull_events()
    assert len(events) == 1
    assert isinstance(events[0], StockAddedToBoard)
    assert events[0].board_id == "test_board"
    assert events[0].parent_path == "테스트보드/하위노드"
    assert events[0].ticker == "005930"
    assert events[0].stock_name == "삼성전자"
    
    # 4. 종목 삭제
    assert board.delete_stock("005930") is True
    events = board.pull_events()
    assert len(events) == 1
    assert isinstance(events[0], StockDeletedFromBoard)
    assert events[0].board_id == "test_board"
    assert events[0].ticker == "005930"
    
    # 5. 노드 삭제
    assert board.delete_node("테스트보드/하위노드") is True
    events = board.pull_events()
    assert len(events) == 1
    assert isinstance(events[0], NodeDeleted)
    assert events[0].board_id == "test_board"
    assert events[0].node_path == "테스트보드/하위노드"

@pytest.mark.unit
def test_board_serialization_ignores_events():
    """pydantic 직렬화 및 역직렬화 수행 시 _events 버퍼가 누출되거나 손상되지 않는지 검증."""
    board = Board(id="test_board", name="테스트보드")
    board.add_node("테스트보드", "하위노드")
    
    # 직렬화
    serialized = board.model_dump_json()
    assert "_events" not in serialized
    
    # 역직렬화
    deserialized = Board.model_validate_json(serialized)
    assert len(deserialized.pull_events()) == 0
