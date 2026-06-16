import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock
from synapstock.application.events.worker import OutboxWorker
from synapstock.domain.events import StockAddedToBoard

@pytest.fixture
def mock_outbox():
    outbox = Mock()
    outbox.load_pending.return_value = []
    return outbox

@pytest.mark.unit
@pytest.mark.asyncio
async def test_worker_processes_pending_event_success(mock_outbox):
    """PENDING 이벤트 발견 시 등록된 핸들러를 실행하고 완료 처리하는지 검증."""
    event_item = {
        "id": "12345_uuid",
        "event": {
            "event_class": "StockAddedToBoard", 
            "data": {
                "ticker": "005930", 
                "board_id": "theme_IT",
                "parent_path": "theme_IT/대장주",
                "stock_name": "삼성전자"
            }
        },
        "status": "PENDING",
        "retry_count": 0
    }
    mock_outbox.load_pending.return_value = [event_item]
    
    mock_handler = AsyncMock()
    handlers = {"StockAddedToBoard": mock_handler}
    
    worker = OutboxWorker(outbox=mock_outbox, handlers=handlers)
    
    await worker.process_pending_events()
    
    mock_handler.assert_called_once()
    called_arg = mock_handler.call_args[0][0]
    assert isinstance(called_arg, StockAddedToBoard)
    assert called_arg.ticker == "005930"
    assert called_arg.board_id == "theme_IT"
    assert called_arg.parent_path == "theme_IT/대장주"
    assert called_arg.stock_name == "삼성전자"
    
    mock_outbox.complete.assert_called_once_with("12345_uuid")

@pytest.mark.unit
@pytest.mark.asyncio
async def test_worker_processes_pending_event_failure_and_retries(mock_outbox):
    """이벤트 처리 실패 시 fail을 마킹하고 재시도를 보류하는지 검증."""
    event_item = {
        "id": "12345_uuid",
        "event": {
            "event_class": "StockAddedToBoard", 
            "data": {
                "ticker": "005930", 
                "board_id": "theme_IT",
                "parent_path": "theme_IT/대장주",
                "stock_name": "삼성전자"
            }
        },
        "status": "PENDING",
        "retry_count": 0,
        "created_at": datetime.now().isoformat()
    }
    mock_outbox.load_pending.return_value = [event_item]
    
    mock_handler = AsyncMock(side_effect=Exception("API Error"))
    handlers = {"StockAddedToBoard": mock_handler}
    
    worker = OutboxWorker(outbox=mock_outbox, handlers=handlers)
    
    await worker.process_pending_events()
    
    mock_outbox.fail.assert_called_once_with("12345_uuid", "API Error")
    mock_outbox.complete.assert_not_called()

@pytest.mark.unit
@pytest.mark.asyncio
async def test_worker_skips_backoff_delay(mock_outbox):
    """지수 백오프 대기 시간 내에 있는 이벤트는 소모를 건너뛰어야 함."""
    event_item = {
        "id": "12345_uuid",
        "event": {
            "event_class": "StockAddedToBoard", 
            "data": {
                "ticker": "005930", 
                "board_id": "theme_IT",
                "parent_path": "theme_IT/대장주",
                "stock_name": "삼성전자"
            }
        },
        "status": "PENDING",
        "retry_count": 1,
        "updated_at": datetime.now().isoformat()  # 방금 업데이트됨 (딜레이 적용 대상)
    }
    mock_outbox.load_pending.return_value = [event_item]
    
    mock_handler = AsyncMock()
    # base_delay를 10초로 지정하여 즉시 처리를 막는다
    worker = OutboxWorker(outbox=mock_outbox, handlers={"StockAddedToBoard": mock_handler}, base_delay=10.0)
    
    await worker.process_pending_events()
    
    mock_handler.assert_not_called()

@pytest.mark.unit
@pytest.mark.asyncio
async def test_worker_failed_permanent_after_max_retries(mock_outbox):
    """최대 재시도(5회) 도달 시, complete 처리하여 더 이상 시도하지 않음."""
    event_item = {
        "id": "12345_uuid",
        "event": {
            "event_class": "StockAddedToBoard", 
            "data": {
                "ticker": "005930", 
                "board_id": "theme_IT",
                "parent_path": "theme_IT/대장주",
                "stock_name": "삼성전자"
            }
        },
        "status": "PENDING",
        "retry_count": 5,  # 이미 5회 도달
        "updated_at": (datetime.now() - timedelta(minutes=10)).isoformat()
    }
    mock_outbox.load_pending.return_value = [event_item]
    
    mock_handler = AsyncMock()
    worker = OutboxWorker(outbox=mock_outbox, handlers={"StockAddedToBoard": mock_handler}, max_retries=5)
    
    await worker.process_pending_events()
    
    mock_handler.assert_not_called()
    mock_outbox.complete.assert_called_once_with("12345_uuid")
