from unittest.mock import Mock, AsyncMock

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

    def delete(self, name: str) -> None:
        if name in self._store:
            del self._store[name]

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
    board = Board(name="theme_data")
    board.add_node("theme_data", "반도체")
    board.add_node("theme_data/반도체", "IDM")

    samsung = Stock(name="삼성전자", ticker="005930", news=[])
    board.add_stock_to_node("theme_data/반도체/IDM", samsung)

    return board


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
    mock_news_service = Mock()
    mock_news_service.save_news = AsyncMock()
    media_service = StockMediaService(repository=repo, storage=storage, news_service=mock_news_service)

    # 1. 경로 검색 기능 검증 (단순 탐색 알고리즘 또는 BoardService 내의 함수 모방)
    # 현재 BoardService에 경로(Path)를 리스트로 반환하는 기능이 없다면,
    # 어댑터/포트 레이어나 라우터에서 다음과 같은 탐색 로직을 사용할 것임을 검증합니다.
    def find_node_path(board: Board, target_name: str) -> list[str]:
        for path_key, node in board.nodes.items():
            for s in node.stocks:
                if s.name == target_name:
                    parts = path_key.split("/")
                    return parts[1:] + [target_name]
        return []

    # 검색 API가 반환할 경로
    board = query_service.load_board("theme_data")
    path = find_node_path(board, "삼성전자")

    assert path == ["반도체", "IDM", "삼성전자"]

    # 2. 경로 쿼리의 뉴스 추가 POST 가 잘 반영되는지 확인
    # /api/news/add/반도체/IDM/삼성전자 와 같은 요청에서 마지막 "삼성전자"(또는 ticker)를 추출하여 추가
    target_ticker = "005930"
    url_to_add = "https://news.example.com/123"

    result = await media_service.add_stock_news(
        board_name="theme_data",
        ticker=target_ticker,
        title="삼성전자 어닝 서프라이즈",
        date="2026-04-01",
        url=url_to_add
    )

    assert result is True

    # 뉴스 저장 호출 검증
    mock_news_service.save_news.assert_called_once_with(
        title="삼성전자 어닝 서프라이즈",
        url=url_to_add,
        ticker=target_ticker,
        stock_name="삼성전자"
    )
