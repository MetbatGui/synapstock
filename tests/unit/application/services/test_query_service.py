from unittest.mock import MagicMock

import pytest

from evenezer.application.services.query_service import BoardQueryService
from evenezer.domain.models import Board, Stock


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

    def test_get_stock_by_ticker_global_search(self, service, mock_repo):
        """여러 보드를 순회하여 티커로 종목을 찾아야 한다."""
        # Arrange
        mock_repo.list_boards.return_value = ["theme_pc", "theme_mobile"]

        # 보드 1: PC (삼성전자 없음)
        board_pc = Board(name="PC")

        # 보드 2: Mobile (삼성전자 있음)
        board_mobile = Board(name="Mobile")
        samsung = Stock(name="삼성전자", ticker="005930")
        board_mobile.add_stock_to_node("Mobile", samsung)

        mock_repo.load.side_effect = [board_pc, board_mobile]

        # Act
        result = service.get_stock_by_ticker("005930")

        # Assert
        assert result is not None
        stock, b_name, path = result
        assert stock.name == "삼성전자"
        assert b_name == "theme_mobile"
        # path는 [보드이름] + [노드이름...] 형태
        assert path == ["Mobile", "Mobile"]
        assert mock_repo.load.call_count == 2

    def test_get_all_stocks_flat(self, service, mock_repo):
        """모든 보드의 종목을 평탄화하여 반환해야 한다."""
        # Arrange
        mock_repo.list_boards.return_value = ["theme_a"]
        board = Board(name="반도체")
        board.add_node("반도체", "메모리")
        board.add_stock_to_node("반도체/메모리", Stock(name="SK하이닉스", ticker="000660"))
        mock_repo.load.return_value = board

        # Act
        flat_list = service.get_all_stocks_flat()

        # Assert
        assert len(flat_list) == 1
        assert flat_list[0]["name"] == "SK하이닉스"
        assert flat_list[0]["path"] == ["반도체", "메모리"]
        assert flat_list[0]["board_name"] == "반도체"

    def test_find_stocks_by_name_global(self, service, mock_repo):
        """종목명 부분 검색이 모든 보드에서 동작해야 한다."""
        # Arrange
        mock_repo.list_boards.return_value = ["theme_a"]
        board = Board(name="반도체")
        board.add_node("반도체", "파운드리")
        board.add_stock_to_node("반도체/파운드리", Stock(name="삼성전자", ticker="005930"))
        mock_repo.load.return_value = board

        # Act
        results = service.find_stocks_by_name("삼성")

        # Assert
        assert len(results) == 1
        assert results[0]["name"] == "삼성전자"
        assert "[반도체] 반도체 > 파운드리 > 삼성전자" in results[0]["path"]
        assert results[0]["board"] == "theme_a"

    def test_find_stocks_by_alias_global(self, service, mock_repo):
        """종목명이 아닌 별칭(aliases)으로도 검색이 가능해야 한다."""
        # Arrange
        mock_repo.list_boards.return_value = ["theme_a"]
        board = Board(name="방산")
        board.add_node("방산", "미사일")
        # 사명은 교체되었고 구 사명이 별칭에 있는 상황
        stock = Stock(name="LIG디펜스앤에어로스페이스", ticker="079550", aliases=["LIG넥스원"])
        board.add_stock_to_node("방산/미사일", stock)
        mock_repo.load.return_value = board

        # Act: 구 사명으로 검색
        results = service.find_stocks_by_name("넥스원")

        # Assert
        assert len(results) == 1
        assert results[0]["name"] == "LIG디펜스앤에어로스페이스"
        assert results[0]["ticker"] == "079550"
        assert "[방산] 방산 > 미사일 > LIG디펜스앤에어로스페이스" in results[0]["path"]
