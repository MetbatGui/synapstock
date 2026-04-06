"""MiroMindmapAdapter 단위 테스트 (Mock 기반).

기존 responses 라이브러리 대신 requests.Session을 직접 모킹하여
네트워크 순서보다는 비즈니스 논리(데이터 생성 유무 등)를 검증합니다.
"""

import pytest
from unittest.mock import MagicMock, patch
from synapstock.adapters.miro.miro_mindmap import MiroMindmapAdapter
from synapstock.domain.models import Board, Node, Stock

@pytest.fixture
def mock_session():
    """requests.Session을 모킹한 객체."""
    session = MagicMock()
    # 기본 성공 응답 설정
    mock_res = MagicMock()
    mock_res.ok = True
    mock_res.status_code = 200
    mock_res.json.return_value = {"data": []}
    session.get.return_value = mock_res
    session.post.return_value = mock_res
    session.patch.return_value = mock_res
    session.delete.return_value = mock_res
    return session

@pytest.fixture
def adapter(mock_session):
    adapter = MiroMindmapAdapter(api_token="fake_token")
    adapter.session = mock_session
    return adapter

def test_list_boards(adapter, mock_session):
    # Arrange
    mock_session.get.return_value.json.return_value = {
        "data": [{"name": "Board 1"}, {"name": "Board 2"}]
    }
    
    # Act
    names = adapter.list_boards()
    
    # Assert
    assert names == ["Board 1", "Board 2"]
    mock_session.get.assert_called_with("https://api.miro.com/v2/boards")

def test_load_board(adapter, mock_session):
    board_name = "Test Board"
    board_id = "b123"
    
    # 세션 호출별 응답 설정 (GET /boards, GET /items, GET /connectors)
    def side_effect(url, **kwargs):
        res = MagicMock()
        res.ok = True
        if "/boards" in url and "/items" not in url and "/connectors" not in url:
            res.json.return_value = {"data": [{"id": board_id, "name": board_name}]}
        elif "/items" in url:
            res.json.return_value = {"data": [
                {"id": "root_id", "type": "shape", "data": {"content": f"<strong>{board_name}</strong>"}},
                {"id": "sub_id", "type": "shape", "data": {"content": "<strong>Sub Node</strong>"}},
                {"id": "stock_id", "type": "shape", "data": {"content": "<strong>Samsung</strong><!--ticker:005930-->"}}
            ], "cursor": None}
        elif "/connectors" in url:
            res.json.return_value = {"data": [
                {"startItem": {"id": "root_id"}, "endItem": {"id": "sub_id"}},
                {"startItem": {"id": "sub_id"}, "endItem": {"id": "stock_id"}}
            ], "cursor": None}
        return res

    mock_session.get.side_effect = side_effect
    
    board = adapter.load(board_name)

    assert board.name == board_name
    assert board.root.name == board_name
    assert len(board.root.nodes) == 1
    assert board.root.nodes[0].stocks[0].ticker == "005930"

def test_save_board_logic(adapter, mock_session):
    """save 호출 시 내부적으로 초기화(delete) 및 생성(post)이 일어나는지 검증."""
    board_name = "Test Board"
    board_id = "b123"
    board = Board(
        name=board_name,
        root=Node(
            name=board_name, depth=0,
            nodes=[Node(name="NodeA", depth=1)],
            stocks=[Stock(name="Stock1", ticker="S1")]
        )
    )

    # 1. GET /boards 응답
    # 2. GET /items (삭제용) 응답
    # 3. POST /shapes 응답 (ID 반환)
    def get_side_effect(url, **kwargs):
        res = MagicMock()
        res.ok = True
        if "items" in url:
            # 처음 호출 시에만 1개 항목 반환 (삭제 로직 테스트)
            if not hasattr(get_side_effect, "called"):
                get_side_effect.called = True
                res.json.return_value = {"data": [{"id": "old_item"}]}
            else:
                res.json.return_value = {"data": []}
        else:
            res.json.return_value = {"data": [{"id": board_id, "name": board_name}]}
        return res

    mock_session.get.side_effect = get_side_effect
    mock_session.post.return_value.json.return_value = {"id": "new_id"}
    
    adapter.save(board)

    # 초기화 확인: DELETE 호출됨?
    assert mock_session.delete.called
    
    # 생성 확인: POST /shapes 호출됨? (현재 구현은 bulk가 아닌 개별 shapes 호출)
    shape_calls = [c for c in mock_session.post.call_args_list if "shapes" in c.args[0]]
    assert len(shape_calls) > 0 # 루트 등 다수 생성됨
    
    # 커넥터 확인: POST /connectors 호출됨?
    conn_calls = [c for c in mock_session.post.call_args_list if "connectors" in c.args[0]]
    assert len(conn_calls) == 2 # (Root->NodeA, NodeA->Stock1)
