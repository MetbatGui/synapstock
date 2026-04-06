import pytest
from unittest.mock import MagicMock
from synapstock.services.query_service import BoardQueryService
from synapstock.domain.models import Board

@pytest.fixture
def mock_repo():
    return MagicMock()

@pytest.fixture
def mock_ticker_search():
    return MagicMock()

@pytest.fixture
def service(mock_repo, mock_ticker_search):
    return BoardQueryService(
        repository=mock_repo,
        ticker_search=mock_ticker_search
    )

class TestBoardQueryService:
    """BoardQueryService 단위 테스트."""

    def test_list_boards(self, service, mock_repo):
        """보드 목록을 정상적으로 조회해야 한다."""
        mock_repo.list_boards.return_value = ["theme_a", "theme_b"]
        
        boards = service.list_boards()
        
        assert boards == ["theme_a", "theme_b"]
        mock_repo.list_boards.assert_called_once()

    def test_load_board(self, service, mock_repo):
        """이름으로 보드를 로드해야 한다."""
        mock_board = Board(name="테스트")
        mock_repo.load.return_value = mock_board
        
        board = service.load_board("theme_a")
        
        assert board.name == "테스트"
        mock_repo.load.assert_called_with("theme_a")

    def test_get_boards_info(self, service, mock_repo):
        """보드 요약 정보를 조회해야 한다."""
        mock_repo.list_boards.return_value = ["theme_a"]
        mock_repo.load.return_value = Board(name="실제이름")
        
        info = service.get_boards_info()
        
        assert len(info) == 1
        assert info[0] == {"id": "theme_a", "name": "실제이름"}

    def test_search_ticker(self, service, mock_ticker_search):
        """티커 검색을 대행해야 한다."""
        mock_ticker_search.search.return_value = [{"name": "삼성전자", "ticker": "005930"}]
        
        results = service.search_ticker("삼성")
        
        assert len(results) == 1
        assert results[0]["ticker"] == "005930"
        mock_ticker_search.search.assert_called_with("삼성")
