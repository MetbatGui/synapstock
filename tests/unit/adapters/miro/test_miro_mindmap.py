"""MiroMindmapAdapter 단위 테스트 (Mock)."""

import pytest
import responses
from synapstock.adapters.miro.miro_mindmap import MiroMindmapAdapter
from synapstock.domain.models import Board, Node, Stock

@pytest.fixture
def adapter():
    return MiroMindmapAdapter(api_token="fake_token")

@responses.activate
def test_list_boards(adapter):
    responses.add(
        responses.GET,
        "https://api.miro.com/v2/boards",
        json={"data": [{"name": "Board 1"}, {"name": "Board 2"}]},
        status=200
    )
    names = adapter.list_boards()
    assert names == ["Board 1", "Board 2"]

@responses.activate
def test_load_board(adapter):
    board_name = "Test Board"
    board_id = "b123"
    
    responses.add(
        responses.GET,
        "https://api.miro.com/v2/boards",
        json={"data": [{"id": board_id, "name": board_name}]},
        status=200
    )
    
    # Items Mock
    responses.add(
        responses.GET,
        f"https://api.miro.com/v2/boards/{board_id}/items?limit=50",
        json={"data": [
            {"id": "root_id", "type": "shape", "data": {"content": f"<strong>{board_name}</strong>"}},
            {"id": "sub_id", "type": "shape", "data": {"content": "<strong>Sub Node</strong>"}},
            {"id": "stock_id", "type": "shape", "data": {"content": "<strong>Samsung</strong><!--ticker:005930-->"}}
        ]},
        status=200
    )
    # 빈 Cursor 응답으로 종료 처리 추가
    responses.add(
        responses.GET,
        f"https://api.miro.com/v2/boards/{board_id}/items?limit=50",
        json={"data": []},
        status=200
    )
    
    # Connectors Mock
    responses.add(
        responses.GET,
        f"https://api.miro.com/v2/boards/{board_id}/connectors?limit=50",
        json={"data": [
            {"startItem": {"id": "root_id"}, "endItem": {"id": "sub_id"}},
            {"startItem": {"id": "sub_id"}, "endItem": {"id": "stock_id"}}
        ]},
        status=200
    )
    
    board = adapter.load(board_name)

    assert board.name == board_name
    assert board.root.name == board_name
    assert len(board.root.nodes) == 1
    assert board.root.nodes[0].name == "Sub Node"
    assert len(board.root.nodes[0].stocks) == 1
    assert board.root.nodes[0].stocks[0].name == "Samsung"
    assert board.root.nodes[0].stocks[0].ticker == "005930"

@responses.activate
def test_save_board_bulk(adapter):
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
    
    responses.add(responses.GET, "https://api.miro.com/v2/boards", json={"data": [{"id": board_id, "name": board_name}]}, status=200)
    
    # Clear items (Mock existing items)
    responses.add(responses.GET, f"https://api.miro.com/v2/boards/{board_id}/items?limit=50", json={"data": [{"id": "old_item"}]}, status=200)
    responses.add(responses.GET, f"https://api.miro.com/v2/boards/{board_id}/items?limit=50", json={"data": []}, status=200)
    responses.add(responses.DELETE, f"https://api.miro.com/v2/boards/{board_id}/items/old_item", status=204)
    
    # Bulk items create mock
    responses.add(
        responses.POST, 
        f"https://api.miro.com/v2/boards/{board_id}/items/bulk",
        json={"data": [{"id": "new_root"}, {"id": "new_node"}, {"id": "new_stock"}]}, 
        status=201
    )
    
    # Connectors mock
    responses.add(responses.POST, f"https://api.miro.com/v2/boards/{board_id}/connectors", json={"id": "conn1"}, status=201)

    adapter.save(board)

    # API 호출 검증
    # GET boards(1) + GET items (2) + DEL old (1) + POST bulk (1) + POST connectors (2) = 7
    assert len(responses.calls) == 7
    bulk_calls = [c for c in responses.calls if "items/bulk" in c.request.url]
    assert len(bulk_calls) == 1
    conn_calls = [c for c in responses.calls if "connectors" in c.request.url and c.request.method == "POST"]
    assert len(conn_calls) == 2
