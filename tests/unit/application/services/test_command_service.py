from unittest.mock import MagicMock

import pytest

from synapstock.application.services.command_service import BoardCommandService
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

    @pytest.mark.asyncio
    async def test_add_stock_success(self, service, mock_repo):
        """부모 노드가 존재할 때 새 종목을 추가하고 저장해야 한다."""
        root = Node(name="Root", depth=0)
        board = Board(name="테스트", root=root)
        mock_repo.load.return_value = board

        success = await service.add_stock("테스트", "Root", "삼성전자", "005930")

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

    @pytest.mark.asyncio
    async def test_delete_stock_success(self, service, mock_repo):
        """특정 티커의 종목을 찾아 삭제하고 저장해야 한다."""
        root = Node(name="Root", depth=0)
        root.stocks.append(Stock(name="삼성전자", ticker="005930"))
        board = Board(name="테스트", root=root)
        mock_repo.load.return_value = board

        success = await service.delete_stock("테스트", "005930")

        assert success is True
        assert len(root.stocks) == 0
        mock_repo.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_batch_ignore_stocks_success(self, service, mock_repo):
        """복수의 티커를 가진 종목들을 일괄 삭제하고 저장해야 한다."""
        root = Node(name="Root", depth=0)
        root.stocks.append(Stock(name="삼성전자", ticker="005930"))
        root.stocks.append(Stock(name="SK하이닉스", ticker="000660"))
        root.stocks.append(Stock(name="카카오", ticker="035720"))
        board = Board(name="virtual_신규상장주", root=root)
        mock_repo.load.return_value = board

        # 동기화 서비스 mock 설정 (비동기 메소드 모킹 대응)
        from unittest.mock import AsyncMock
        mock_sync = MagicMock()
        mock_sync.handle_batch_stock_deletion_trigger = AsyncMock()
        mock_sync.sync_with_drive = AsyncMock()
        service._sync_service = mock_sync

        tickers_to_delete = ["005930", "000660"]
        success = await service.batch_ignore_stocks("virtual_신규상장주", tickers_to_delete)

        assert success is True
        assert len(root.stocks) == 1
        assert root.stocks[0].ticker == "035720"  # 카카오만 남음
        mock_repo.save.assert_called_once()
        mock_sync.update_local_manifest.assert_called_once_with("virtual_신규상장주", deleted=False)
        mock_sync.handle_batch_stock_deletion_trigger.assert_called_once_with(tickers_to_delete, "virtual_신규상장주")
        mock_sync.sync_with_drive.assert_called_once()
