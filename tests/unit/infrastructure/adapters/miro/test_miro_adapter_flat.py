"""플랫 도메인 개편에 대응하는 MiroMindmapAdapter 레이아웃 연산 및 로드 테스트."""

from unittest.mock import MagicMock

import pytest

from synapstock.domain.models import Board, Stock
from synapstock.infrastructure.adapters.miro.miro_mindmap import MiroMindmapAdapter


@pytest.fixture
def mock_session():
    session = MagicMock()
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


class TestMiroMindmapAdapterFlat:
    """MiroMindmapAdapter가 플랫 Board 구조를 바탕으로 정상 연산하는지 검증."""

    def test_calculate_balanced_layout_with_flat_board(self, adapter):
        """플랫 Board 구조를 전달받았을 때, _calculate_balanced_layout가 정상적으로 좌우 균형 레이아웃 좌표 리스트를 계산해야 한다."""
        board = Board(name="Theme_IT")
        # 구조: IT (Root) -> 인터넷 (stocks: NAVER)
        #                 -> 게임 (stocks: 크래프톤)
        board.add_node("Theme_IT", "인터넷")
        board.add_stock_to_node("Theme_IT/인터넷", Stock(name="NAVER", ticker="035420"))
        
        board.add_node("Theme_IT", "게임")
        board.add_stock_to_node("Theme_IT/게임", Stock(name="크래프톤", ticker="259960"))

        # Act: 레이아웃 계산 실행
        # 리팩토링된 어댑터의 _calculate_balanced_layout는 board를 통째로 받거나 board.root가 아닌 board.nodes를 바탕으로 연산
        layout = adapter._calculate_balanced_layout(board)

        # Assert: 레이아웃 결과가 잘 나왔는지 검증
        # 총 5개 요소 (IT, 인터넷, NAVER, 게임, 크래프톤)
        assert len(layout) == 5

        # 각 항목의 구성 요소 확인: (obj, depth, x, y, is_stock)
        root_item = next((item for item in layout if item[1] == 0), None)
        assert root_item is not None
        assert root_item[0].name == "Theme_IT"
        assert root_item[2] == 0  # 루트 X는 0
        assert root_item[3] == 0  # 루트 Y는 0

        # 자식 노드들이 존재해야 함
        internet_item = next((item for item in layout if getattr(item[0], "name", "") == "인터넷"), None)
        assert internet_item is not None
        assert internet_item[1] == 1  # 1depth
        
        naver_item = next((item for item in layout if getattr(item[0], "name", "") == "NAVER"), None)
        assert naver_item is not None
        assert naver_item[1] == 2  # 2depth (Stock)
        assert naver_item[4] is True  # is_stock

    def test_load_board_populates_flat_nodes_dict(self, adapter, mock_session):
        """Miro API 데이터를 로드 시, 반환되는 Board의 nodes 딕셔너리가 올바른 절대 경로 키 형태로 채워져야 한다."""
        board_name = "Theme_IT"
        board_id = "b123"

        # GET 호출 시의 Mock 응답 설정
        def side_effect(url, **kwargs):
            res = MagicMock()
            res.ok = True
            if "/boards" in url and "/items" not in url and "/connectors" not in url:
                res.json.return_value = {"data": [{"id": board_id, "name": board_name}]}
            elif "/items" in url:
                res.json.return_value = {
                    "data": [
                        {"id": "r1", "type": "shape", "data": {"content": f"<strong>{board_name}</strong>"}},
                        {"id": "c1", "type": "shape", "data": {"content": "<strong>인터넷</strong>"}},
                        {"id": "s1", "type": "shape", "data": {"content": "<strong>NAVER</strong><!--ticker:035420-->"}}
                    ],
                    "cursor": None
                }
            elif "/connectors" in url:
                res.json.return_value = {
                    "data": [
                        {"startItem": {"id": "r1"}, "endItem": {"id": "c1"}},
                        {"startItem": {"id": "c1"}, "endItem": {"id": "s1"}}
                    ],
                    "cursor": None
                }
            return res

        mock_session.get.side_effect = side_effect

        # Act: 로드 집행
        board = adapter.load(board_name)

        # Assert: 플랫 맵 형태로 로드되었는지 검증
        assert board.name == board_name
        assert len(board.nodes) == 2  # Theme_IT (루트), Theme_IT/인터넷
        
        # 루트 노드 검증
        assert "Theme_IT" in board.nodes
        assert board.nodes["Theme_IT"].depth == 0
        
        # 자식 노드 및 주식 검증
        assert "Theme_IT/인터넷" in board.nodes
        child_node = board.nodes["Theme_IT/인터넷"]
        assert child_node.depth == 1
        assert child_node.parent_path == "Theme_IT"
        assert len(child_node.stocks) == 1
        assert child_node.stocks[0].ticker == "035420"
