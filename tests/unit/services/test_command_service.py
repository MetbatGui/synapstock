import pytest
from unittest.mock import MagicMock
from synapstock.services.command_service import BoardCommandService
from synapstock.domain.models import Board, Node, Stock

@pytest.fixture
def mock_repo():
    return MagicMock()

@pytest.fixture
def service(mock_repo):
    return BoardCommandService(repository=mock_repo)

class TestBoardCommandService:
    """BoardCommandService 단위 테스트."""

    def test_add_node_success(self, service, mock_repo):
        """부모 노드가 존재할 때 새 노드를 추가하고 저장해야 한다."""
        root = Node(name="Root", depth=0)
        board = Board(name="테스트", root=root)
        mock_repo.load.return_value = board
        
        success = service.add_node("테스트", "Root", "NewNode")
        
        assert success is True
        assert len(root.nodes) == 1
        assert root.nodes[0].name == "NewNode"
        mock_repo.save.assert_called_once()

    def test_add_stock_success(self, service, mock_repo):
        """부모 노드가 존재할 때 새 종목을 추가하고 저장해야 한다."""
        root = Node(name="Root", depth=0)
        board = Board(name="테스트", root=root)
        mock_repo.load.return_value = board
        
        success = service.add_stock("테스트", "Root", "삼성전자", "005930")
        
        assert success is True
        assert len(root.stocks) == 1
        assert root.stocks[0].name == "삼성전자"
        mock_repo.save.assert_called_once()

    def test_delete_node_success(self, service, mock_repo):
        """노드를 삭제하고 저장해야 한다."""
        root = Node(name="Root", depth=0)
        child = root.add_child("Target")
        board = Board(name="테스트", root=root)
        mock_repo.load.return_value = board
        
        success = service.delete_node("테스트", "Target")
        
        assert success is True
        assert len(root.nodes) == 0
        mock_repo.save.assert_called_once()

    def test_delete_stock_success(self, service, mock_repo):
        """특정 티커의 종목을 찾아 삭제하고 저장해야 한다."""
        root = Node(name="Root", depth=0)
        root.stocks.append(Stock(name="삼성전자", ticker="005930"))
        board = Board(name="테스트", root=root)
        mock_repo.load.return_value = board
        
        success = service.delete_stock("테스트", "005930")
        
        assert success is True
        assert len(root.stocks) == 0
        mock_repo.save.assert_called_once()
