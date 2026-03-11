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
    # Given
    responses.add(
        responses.GET,
        "https://api.miro.com/v2/boards",
        json={"data": [{"name": "Board 1"}, {"name": "Board 2"}]},
        status=200
    )

    # When
    names = adapter.list_boards()

    # Then
    assert names == ["Board 1", "Board 2"]

@responses.activate
def test_load_board(adapter):
    # Given
    board_name = "Test Board"
    board_id = "b123"
    shape_id = "s456"
    
    # 1. 보드 ID 조회 모킹
    responses.add(
        responses.GET,
        "https://api.miro.com/v2/boards",
        json={"data": [{"id": board_id, "name": board_name}]},
        status=200
    )
    # 2. 아이템 조회 (Shape 1개, Card 1개)
    responses.add(
        responses.GET,
        f"https://api.miro.com/v2/boards/{board_id}/items",
        json={"data": [
            {"id": shape_id, "type": "shape", "data": {"content": board_name}},
            {"id": "c789", "type": "card", "data": {"title": "Samsung", "description": "005930"}}
        ]},
        status=200
    )
    # 3. 커넥터 조회 (Shape -> Card 연결 1개)
    responses.add(
        responses.GET,
        f"https://api.miro.com/v2/boards/{board_id}/connectors",
        json={"data": [
            {"id": "conn1", "startItem": {"id": shape_id}, "endItem": {"id": "c789"}}
        ]},
        status=200
    )

    # When
    board = adapter.load(board_name)

    # Then
    assert board.name == board_name
    assert board.root.name == board_name
    assert len(board.root.stocks) == 1
    assert board.root.stocks[0].name == "Samsung"
    assert board.root.stocks[0].ticker == "005930"

@responses.activate
def test_save_board_reconciliation(adapter):
    # Given
    board_name = "Test Board"
    board_id = "b123"
    # 도메인 트리: Root -> NodeA -> Stock1
    board = Board(
        name=board_name,
        root=Node(
            name=board_name, depth=0,
            nodes=[Node(name="NodeA", depth=1)],
            stocks=[Stock(name="Stock1", ticker="S1")]
        )
    )
    
    # 1. 보드 ID 조회
    responses.add(responses.GET, "https://api.miro.com/v2/boards",
                  json={"data": [{"id": board_id, "name": board_name}]}, status=200)
    
    # 2. 현재 상태 Fetch (Miro에는 Root만 있고 자식은 없는 상태)
    responses.add(responses.GET, f"https://api.miro.com/v2/boards/{board_id}/items",
                  json={"data": [{"id": "root_id", "type": "shape", "data": {"content": board_name}}]}, status=200)
    responses.add(responses.GET, f"https://api.miro.com/v2/boards/{board_id}/connectors",
                  json={"data": []}, status=200)
    
    # 3. 새로운 NodeA 생성 (Shape)
    responses.add(responses.POST, f"https://api.miro.com/v2/boards/{board_id}/shapes",
                  json={"id": "node_a_id"}, status=201)
    # 4. 새로운 Stock1 생성 (Card)
    responses.add(responses.POST, f"https://api.miro.com/v2/boards/{board_id}/cards",
                  json={"id": "stock_1_id"}, status=201)
    # 5. Connectors 생성 (Root->NodeA, Root->Stock1)
    responses.add(responses.POST, f"https://api.miro.com/v2/boards/{board_id}/connectors",
                  json={"id": "conn1"}, status=201)
    responses.add(responses.POST, f"https://api.miro.com/v2/boards/{board_id}/connectors",
                  json={"id": "conn2"}, status=201)

    # When
    adapter.save(board)

    # Then
    # API 호출 횟수 및 순서 확인
    # GET (boards, items, connectors) + POST (shape, card, conn, conn)
    assert len(responses.calls) == 7
    
    post_cards = [c for c in responses.calls if c.request.method == 'POST' and '/cards' in c.request.url]
    assert len(post_cards) == 1
    assert "Stock1" in post_cards[0].request.body.decode()
