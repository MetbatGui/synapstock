"""MiroMindmapAdapter 단위 테스트 (Mock)."""

import pytest
import responses
from synapstock.adapters.miro.miro_mindmap import MiroMindmapAdapter
from synapstock.domain.models import Board, Node

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
    # 2. 아이템 조회 (Shape 1개)
    responses.add(
        responses.GET,
        f"https://api.miro.com/v2/boards/{board_id}/items",
        json={"data": [{"id": shape_id, "type": "shape", "data": {"content": board_name}}]},
        status=200
    )
    # 3. 커넥터 조회 (0개)
    responses.add(
        responses.GET,
        f"https://api.miro.com/v2/boards/{board_id}/connectors",
        json={"data": []},
        status=200
    )

    # When
    board = adapter.load(board_name)

    # Then
    assert board.name == board_name
    assert board.root.name == board_name
    assert len(board.root.nodes) == 0

@responses.activate
def test_save_board(adapter):
    # Given
    board_name = "Test Board"
    board_id = "b123"
    board = Board(name=board_name, root=Node(name="Root", depth=0))
    
    # 1. 보드 ID 조회
    responses.add(
        responses.GET,
        "https://api.miro.com/v2/boards",
        json={"data": [{"id": board_id, "name": board_name}]},
        status=200
    )
    # 2. 기존 아이템 조회 (1개)
    responses.add(
        responses.GET,
        f"https://api.miro.com/v2/boards/{board_id}/items",
        json={"data": [{"id": "old_id"}]},
        status=200
    )
    # 3. 삭제
    responses.add(
        responses.DELETE,
        f"https://api.miro.com/v2/boards/{board_id}/items/old_id",
        status=204
    )
    # 4. 새 Shape 생성
    responses.add(
        responses.POST,
        f"https://api.miro.com/v2/boards/{board_id}/shapes",
        json={"id": "new_shape_id"},
        status=201
    )

    # When
    adapter.save(board)

    # Then
    # responses.calls를 통해 각 API가 호출되었는지 검증 가능
    assert len(responses.calls) == 4 # GET boards, GET items, DELETE items, POST shapes
