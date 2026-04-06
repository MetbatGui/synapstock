"""BoardService 단위 테스트."""

from unittest.mock import MagicMock

import pytest

from synapstock.domain.models import Board, Stock
from synapstock.services.board_service import BoardService


@pytest.fixture
def mock_mindmap():
    """MindmapPort Mock 픽스처."""
    return MagicMock()


@pytest.fixture
def mock_repo():
    """BoardRepositoryPort Mock 픽스처."""
    return MagicMock()


@pytest.fixture
def mock_ticker_search():
    """TickerSearchPort Mock 픽스처."""
    return MagicMock()


@pytest.fixture
def mock_storage():
    """StoragePort Mock 픽스처."""
    mock = MagicMock()
    mock.put_file.return_value = True
    return mock


@pytest.fixture
def service(mock_repo, mock_mindmap, mock_ticker_search, mock_storage):
    """BoardService 픽스처."""
    return BoardService(
        repository=mock_repo, 
        mindmap=mock_mindmap, 
        ticker_search=mock_ticker_search,
        storage=mock_storage
    )


@pytest.fixture
def it_board() -> Board:
    """IT 보드 픽스처."""
    board = Board(name="IT")
    internet = board.root.add_child("인터넷")
    internet.stocks.append(Stock(name="NAVER", ticker="035420"))
    return board


class TestBoardService:
    """BoardService 기본 동작 테스트."""

    def test_load_delegates_to_repo(self, service, mock_repo, it_board):
        """load()는 BoardRepositoryPort.load()를 호출하고 결과를 그대로 반환해야 한다.

        Arrange: BoardRepositoryPort Mock이 it_board를 반환하도록 설정
        Act: service.load("IT") 호출
        Assert: Mock이 정확히 1회 호출됐는지, 반환값이 동일 객체인지 확인
        """
        mock_repo.load.return_value = it_board

        result = service.load("IT")

        mock_repo.load.assert_called_once_with("IT")
        assert result is it_board

    def test_save_delegates_to_mindmap(self, service, mock_mindmap, it_board):
        """save()는 MindmapPort.save()에 Board를 전달해야 한다.

        Arrange: 저장할 it_board 픽스처 준비
        Act: service.save(it_board) 호출
        Assert: Mock이 it_board를 인자로 1회 호출됐는지 확인
        """
        service.save(it_board)

        mock_mindmap.save.assert_called_once_with(it_board, progress_callback=None)

    def test_list_boards_delegates_to_repo(self, service, mock_repo):
        """list_boards()는 BoardRepositoryPort.list_boards() 결과를 그대로 반환해야 한다.

        Arrange: BoardRepositoryPort Mock이 보드 이름 목록을 반환하도록 설정
        Act: service.list_boards() 호출
        Assert: Mock 호출 여부 및 반환값 일치 확인
        """
        mock_repo.list_boards.return_value = ["IT", "바이오"]

        result = service.list_boards()

        mock_repo.list_boards.assert_called_once()
        assert result == ["IT", "바이오"]

    def test_load_not_found_propagates(self, service, mock_repo):
        """BoardRepositoryPort.load()가 FileNotFoundError를 발생시키면 그대로 전파되어야 한다.

        Arrange: BoardRepositoryPort Mock이 FileNotFoundError를 발생하도록 설정
        Act: service.load("없는보드") 호출
        Assert: FileNotFoundError가 호출자까지 전파되는지 확인
        """
        mock_repo.load.side_effect = FileNotFoundError("없는보드")

        with pytest.raises(FileNotFoundError, match="없는보드"):
            service.load("없는보드")

    def test_load_returns_board_with_tree(self, service, mock_repo, it_board):
        """load() 결과 Board는 노드 트리 구조를 유지해야 한다.

        Arrange: BoardRepositoryPort Mock이 트리 구조를 가진 it_board를 반환하도록 설정
        Act: service.load("IT") 호출
        Assert: 반환된 Board의 루트 노드 및 자식 노드 구조가 올바른지 확인
        """
        mock_repo.load.return_value = it_board

        result = service.load("IT")

        assert result.root.name == "IT"
        assert result.root.depth == 0
        internet = next(n for n in result.root.nodes if n.name == "인터넷")
        assert internet.stocks[0].ticker == "035420"

    def test_add_stock_report_delegates_to_storage(self, service, mock_storage, mock_repo, it_board):
        """add_stock_report()는 StoragePort.put_file()을 호출하여 파일을 저장해야 한다.

        Arrange:
            저장할 파일 내용과 이름을 준비한다. 레포지토리가 it_board를 반환하도록 설정한다.
        Act:
            service.add_stock_report()를 호출한다.
        Assert:
            1. storage.put_file()이 올바른 경로와 내용으로 호출되었는지 확인한다.
            2. 레포지토리에 보드 변경사항이 저장되었는지 확인한다.
        """
        mock_repo.load.return_value = it_board
        content = b"pdf content"
        filename = "report.pdf"
        
        success = service.add_stock_report("IT", "035420", content, filename)
        
        # storage 호출 확인
        mock_storage.put_file.assert_called_once_with("data/pdf/report.pdf", content)
        # repo 저장 확인
        mock_repo.save.assert_called_once()
        assert success is True

