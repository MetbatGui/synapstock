from unittest.mock import Mock

import pytest

from synapstock.application.services.media_service import StockMediaService
from synapstock.application.services.query_service import BoardQueryService
from synapstock.domain.models import Board, Node, Stock
from synapstock.domain.ports import BoardRepositoryPort, MindmapPort, StoragePort, TickerSearchPort


class MockBoardRepository(BoardRepositoryPort):
    def __init__(self):
        self._store = {}

    def load(self, name: str) -> Board:
        if name not in self._store:
            raise FileNotFoundError()
        return self._store[name]

    def save(self, board: Board) -> None:
        self._store[board.name] = board

    def list_boards(self) -> list[str]:
        return list(self._store.keys())

class MockMindmapAdapter(MindmapPort):
    def load(self, board_name: str, progress_callback=None) -> Board:
        pass
    def save(self, board: Board, progress_callback=None) -> None:
        pass
    def list_boards(self) -> list[str]:
        return []
    def sync(self, board: Board, progress_callback=None) -> None:
        pass


@pytest.fixture
def mock_board():
    root = Node(name="Root", depth=0)

    # 반도체 > IDM > 삼성전자
    semi_node = root.add_child("반도체")
    idm_node = semi_node.add_child("IDM")

    samsung = Stock(name="삼성전자", ticker="005930", news=[])
    idm_node.stocks.append(samsung)

    return Board(name="theme_data", root=root)

@pytest.mark.asyncio
async def test_search_path_and_add_news(mock_board):
    """
    사용자가 '삼성전자'를 검색하여 종목 경로를 파악하고, 
    해당 종목에 뉴스 링크를 추가(POST)하는 일련의 워크플로우를 테스트합니다.
    """
    repo = MockBoardRepository()
    repo.save(mock_board)

    mindmap = MockMindmapAdapter()
    ticker_search = Mock(spec=TickerSearchPort)
    storage = Mock(spec=StoragePort)

    query_service = BoardQueryService(repository=repo, ticker_search=ticker_search)
    media_service = StockMediaService(repository=repo, storage=storage)

    # 1. 경로 검색 기능 검증 (단순 탐색 알고리즘 또는 BoardService 내의 함수 모방)
    # 현재 BoardService에 경로(Path)를 리스트로 반환하는 기능이 없다면,
    # 어댑터/포트 레이어나 라우터에서 다음과 같은 탐색 로직을 사용할 것임을 검증합니다.
    def find_node_path(node: Node, target_name: str, current_path: list[str]) -> list[str]:
        for s in node.stocks:
            if s.name == target_name:
                return current_path + [target_name]
        for child in node.nodes:
            res = find_node_path(child, target_name, current_path + [child.name])
            if res:
                return res
        return []

    # 검색 API가 반환할 경로
    board = query_service.load_board("theme_data")
    path = find_node_path(board.root, "삼성전자", [])

    assert path == ["반도체", "IDM", "삼성전자"]

    # 2. 경로 쿼리의 뉴스 추가 POST 가 잘 반영되는지 확인
    # /api/news/add/반도체/IDM/삼성전자 와 같은 요청에서 마지막 "삼성전자"(또는 ticker)를 추출하여 추가
    target_ticker = "005930"

    # 추가 전 확인
    samsung_node = query_service.find_node_by_name(board.root, "IDM") # 삼성전자가 속한 부모 등
    assert len(samsung_node.stocks[0].news) == 0

    # 뉴스 추가 (경로 또는 티커 기반. StockMediaService.add_stock_news 이용)
    url_to_add = "https://news.example.com/123"
    result = await media_service.add_stock_news(
        board_name="theme_data",
        ticker=target_ticker,
        title="삼성전자 어닝 서프라이즈",
        date="2026-04-01",
        url=url_to_add
    )

    assert result is True

    # 뉴스 배열(news []) 업데이트 확인
    updated_board = query_service.load_board("theme_data")
    updated_parent_node = query_service.find_node_by_name(updated_board.root, "IDM")
    updated_stock = next(s for s in updated_parent_node.stocks if s.ticker == target_ticker)

    assert len(updated_stock.news) == 1
    assert updated_stock.news[0]["url"] == url_to_add
    assert updated_stock.news[0]["title"] == "삼성전자 어닝 서프라이즈"
