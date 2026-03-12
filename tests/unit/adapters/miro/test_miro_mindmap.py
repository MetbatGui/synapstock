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
    root_id = "root_1"
    sub_id = "sub_1"
    card_id = "card_1"
    
    # 1. 보드 ID 조회 모킹
    responses.add(
        responses.GET,
        "https://api.miro.com/v2/boards",
        json={"data": [{"id": board_id, "name": board_name}]},
        status=200
    )
    
    # 2. 아이템 조회 (mindmap_nodes)
    # Root, SubNode, Card
    responses.add(
        responses.GET,
        f"https://api.miro.com/v2-experimental/boards/{board_id}/mindmap_nodes",
        json={"data": [
            {"id": root_id, "data": {"nodeView": {"data": {"content": board_name}}}},
            {"id": sub_id, "data": {"nodeView": {"data": {"content": "Sub Node"}}}, "parent": {"id": root_id}},
            {"id": card_id, "data": {"nodeView": {"data": {"content": "Samsung<!--ticker:005930-->"}}}, "parent": {"id": sub_id}}
        ]},
        status=200
    )

    # When
    board = adapter.load(board_name)

    # Then
    assert board.name == board_name
    assert board.root.name == board_name
    assert len(board.root.nodes) == 1
    assert board.root.nodes[0].name == "Sub Node"
    assert len(board.root.nodes[0].stocks) == 1
    assert board.root.nodes[0].stocks[0].name == "Samsung"
    assert board.root.nodes[0].stocks[0].ticker == "005930"

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
    responses.add(responses.GET, f"https://api.miro.com/v2-experimental/boards/{board_id}/mindmap_nodes",
                  json={"data": [{"id": "root_id", "data": {"nodeView": {"data": {"content": board_name}}}}]}, status=200)
    
    # 3. 새로운 NodeA, Stock1 생성 시도 (mindmap_nodes POST)
    responses.add(responses.POST, f"https://api.miro.com/v2-experimental/boards/{board_id}/mindmap_nodes",
                  json={"id": "new_created_id"}, status=201)

    # When
    adapter.save(board)

    # Then
    # API 호출 횟수 및 순서 확인
    # GET (boards, mindmap_nodes) + POST (NodeA, Stock1) = 4회
    assert len(responses.calls) == 4
    
    post_nodes = [c for c in responses.calls if c.request.method == 'POST' and 'mindmap_nodes' in c.request.url]
    assert len(post_nodes) == 2
    # Stock 생성 바디 확인
    post_bodies = [c.request.body.decode() for c in post_nodes]
    assert any("Stock1" in body and "S1" in body for body in post_bodies)
