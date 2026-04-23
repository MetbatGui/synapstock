from unittest.mock import MagicMock

import pytest

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

    def test_name_migration_on_normalization(self, service, mock_ticker_search):
        """정규화 과정에서 사명 변경이 감지되면 새 사명으로 교체하고 구 사명을 별칭으로 이동시켜야 한다."""
        root = Node(name="Root", depth=0)
        # 티커는 있지만 이름이 구 사명인 경우
        stock = Stock(name="LIG넥스원", ticker="079550")
        root.stocks.append(stock)
        board = Board(name="테스트", root=root)

        # 네이버 API는 새 사명을 반환한다고 가정
        mock_ticker_search.search.return_value = [{"name": "LIG디펜스앤에어로스페이스", "ticker": "079550"}]

        service._normalize_board_tickers(board, progress_callback=None)

        assert stock.name == "LIG디펜스앤에어로스페이스"
        assert "LIG넥스원" in stock.aliases
        assert len(stock.aliases) == 1
