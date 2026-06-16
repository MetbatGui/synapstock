from unittest.mock import MagicMock
import pytest

from evenezer.application.services.command_service import BoardCommandService
from evenezer.domain.models import Board, Stock
from evenezer.domain.events import (
    NodeAdded, NodeDeleted, StockAddedToBoard, StockDeletedFromBoard,
    BoardCreated, BoardDeleted, BatchStocksDeletedFromBoard
)


@pytest.fixture
def mock_repo():
    return MagicMock()


@pytest.fixture
def mock_event_bus():
    from unittest.mock import AsyncMock
    bus = MagicMock()
    bus.publish_async = AsyncMock()
    return bus


@pytest.fixture
def service(mock_repo, mock_event_bus):
    return BoardCommandService(repository=mock_repo, event_bus=mock_event_bus)


class TestBoardCommandService:
    """BoardCommandService 단위 테스트."""

    def test_add_node_success(self, service, mock_repo, mock_event_bus):
        """부모 노드가 존재할 때 새 노드를 추가하고 저장한 뒤 이벤트를 발행해야 한다."""
        board = Board(id="테스트", name="테스트")
        mock_repo.load.return_value = board

        success = service.add_node("테스트", "테스트", "NewNode")

        assert success is True
        assert "테스트/NewNode" in board.nodes
        mock_repo.save.assert_called_once()
        
        # 이벤트 발행 검증 (동기 발행)
        mock_event_bus.publish.assert_called_once()
        event = mock_event_bus.publish.call_args[0][0]
        assert isinstance(event, NodeAdded)
        assert event.board_id == "테스트"
        assert event.parent_path == "테스트"
        assert event.node_name == "NewNode"

    @pytest.mark.asyncio
    async def test_add_stock_success(self, service, mock_repo, mock_event_bus):
        """부모 노드가 존재할 때 새 종목을 추가하고 저장한 뒤 이벤트를 발행해야 한다."""
        board = Board(id="테스트", name="테스트")
        mock_repo.load.return_value = board

        success = await service.add_stock("테스트", "테스트", "삼성전자", "005930")

        assert success is True
        assert len(board.nodes["테스트"].stocks) == 1
        assert board.nodes["테스트"].stocks[0].name == "삼성전자"
        mock_repo.save.assert_called_once()
        
        # 이벤트 발행 검증 (비동기 발행)
        mock_event_bus.publish_async.assert_called_once()
        event = mock_event_bus.publish_async.call_args[0][0]
        assert isinstance(event, StockAddedToBoard)
        assert event.board_id == "테스트"
        assert event.parent_path == "테스트"
        assert event.ticker == "005930"
        assert event.stock_name == "삼성전자"

    def test_delete_node_success(self, service, mock_repo, mock_event_bus):
        """노드를 삭제하고 저장한 뒤 이벤트를 발행해야 한다."""
        board = Board(id="테스트", name="테스트")
        board.add_node("테스트", "Target")
        # 노드 생성 이벤트 비우기
        board.pull_events()
        
        mock_repo.load.return_value = board

        success = service.delete_node("테스트", "Target")

        assert success is True
        assert "테스트/Target" not in board.nodes
        mock_repo.save.assert_called_once()
        
        # 이벤트 발행 검증 (동기 발행)
        mock_event_bus.publish.assert_called_once()
        event = mock_event_bus.publish.call_args[0][0]
        assert isinstance(event, NodeDeleted)
        assert event.board_id == "테스트"
        assert event.node_path == "테스트/Target"

    @pytest.mark.asyncio
    async def test_delete_stock_success(self, service, mock_repo, mock_event_bus):
        """특정 티커의 종목을 찾아 삭제하고 저장한 뒤 이벤트를 발행해야 한다."""
        board = Board(id="테스트", name="테스트")
        board.add_stock_to_node("테스트", Stock(name="삼성전자", ticker="005930"))
        # 종목 추가 이벤트 비우기
        board.pull_events()
        
        mock_repo.load.return_value = board

        success = await service.delete_stock("테스트", "005930")

        assert success is True
        assert len(board.nodes["테스트"].stocks) == 0
        mock_repo.save.assert_called_once()
        
        # 이벤트 발행 검증 (비동기 발행)
        mock_event_bus.publish_async.assert_called_once()
        event = mock_event_bus.publish_async.call_args[0][0]
        assert isinstance(event, StockDeletedFromBoard)
        assert event.board_id == "테스트"
        assert event.ticker == "005930"

    @pytest.mark.asyncio
    async def test_batch_ignore_stocks_success(self, service, mock_repo, mock_event_bus):
        """복수의 티커를 가진 종목들을 일괄 삭제하고 저장한 뒤 이벤트를 발행해야 한다."""
        board = Board(id="virtual_신규상장주", name="virtual_신규상장주")
        board.add_stock_to_node("virtual_신규상장주", Stock(name="삼성전자", ticker="005930"))
        board.add_stock_to_node("virtual_신규상장주", Stock(name="SK하이닉스", ticker="000660"))
        board.add_stock_to_node("virtual_신규상장주", Stock(name="카카오", ticker="035720"))
        # 이벤트 비우기
        board.pull_events()
        
        mock_repo.load.return_value = board

        tickers_to_delete = ["005930", "000660"]
        success = await service.batch_ignore_stocks("virtual_신규상장주", tickers_to_delete)

        assert success is True
        assert len(board.nodes["virtual_신규상장주"].stocks) == 1
        assert board.nodes["virtual_신규상장주"].stocks[0].ticker == "035720"  # 카카오만 남음
        mock_repo.save.assert_called_once()
        
        # 이벤트 발행 검증 (비동기 발행)
        mock_event_bus.publish_async.assert_called_once()
        event = mock_event_bus.publish_async.call_args[0][0]
        assert isinstance(event, BatchStocksDeletedFromBoard)
        assert event.board_id == "virtual_신규상장주"
        assert event.tickers == tickers_to_delete
