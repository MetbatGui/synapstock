import pytest
from unittest.mock import MagicMock
from synapstock.application.services.sync_service import BoardSyncService
from synapstock.domain.models import Board, Node, Stock

@pytest.fixture
def mock_mindmap():
    return MagicMock()

@pytest.fixture
def mock_ticker_search():
    return MagicMock()

@pytest.fixture
def service(mock_mindmap, mock_ticker_search):
    return BoardSyncService(
        mindmap=mock_mindmap,
        ticker_search=mock_ticker_search
    )

class TestBoardSyncService:
    """BoardSyncService 단위 테스트."""

    def test_normalize_board_tickers(self, service, mock_ticker_search):
        """티커가 부정확한 종목의 티커를 자동으로 검색하여 채워넣어야 한다."""
        root = Node(name="Root", depth=0)
        # 티커가 잘못됨
        root.stocks.append(Stock(name="삼성전자", ticker="ERROR")) 
        board = Board(name="테스트", root=root)
        
        mock_ticker_search.search.return_value = [{"name": "삼성전자", "ticker": "005930"}]
        
        service._normalize_board_tickers(board, progress_callback=None)
        
        assert root.stocks[0].ticker == "005930"
        mock_ticker_search.search.assert_called_with("삼성전자")

    def test_sync_with_miro_calls_normalize_and_sync(self, service, mock_mindmap, mock_ticker_search):
        """sync_with_miro는 정규화와 동기화를 모두 호출해야 한다."""
        root = Node(name="Root", depth=0)
        root.stocks.append(Stock(name="삼성전자", ticker="005930"))
        board = Board(name="테스트", root=root)
        
        service.sync_with_miro(board, progress_callback=None)
        
        mock_mindmap.sync.assert_called_once_with(board, progress_callback=None)
