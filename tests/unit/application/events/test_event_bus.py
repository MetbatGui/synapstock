import asyncio
import pytest
from unittest.mock import Mock
from evenezer.domain.ports import EventBusPort
from evenezer.infrastructure.adapters.events.in_memory_bus import InMemoryEventBusAdapter

@pytest.mark.unit
def test_event_bus_interface():
    """InMemoryEventBusAdapter가 EventBusPort의 인스턴스인지 검증."""
    bus = InMemoryEventBusAdapter()
    assert isinstance(bus, EventBusPort)

@pytest.mark.unit
def test_subscribe_and_publish_sync_handler():
    """동기 이벤트 핸들러가 정상적으로 구독 및 발행되어 호출되는지 검증."""
    bus = InMemoryEventBusAdapter()
    
    class DummyEvent:
        def __init__(self, value: str):
            self.value = value
            
    mock_handler = Mock()
    bus.subscribe(DummyEvent, mock_handler)
    
    event = DummyEvent("sync_test")
    bus.publish(event)
    
    mock_handler.assert_called_once_with(event)

@pytest.mark.unit
@pytest.mark.asyncio
async def test_subscribe_and_publish_async_handler():
    """비동기 이벤트 핸들러가 publish 호출 시 백그라운드로 예약되어 비동기 실행되는지 검증."""
    bus = InMemoryEventBusAdapter()
    
    class DummyEvent:
        def __init__(self, value: str):
            self.value = value

    called_event = None
    async def async_handler(event: DummyEvent):
        nonlocal called_event
        await asyncio.sleep(0.01)
        called_event = event

    bus.subscribe(DummyEvent, async_handler)
    
    event = DummyEvent("async_test")
    
    # publish 자체는 동기 함수이므로 백그라운드 태스크로 create_task가 돌게 됨
    bus.publish(event)
    
    # publish 직후에는 비동기 대기가 없었으므로 아직 완료되지 않은 상태
    assert called_event is None
    
    # 0.02초 대기하여 이벤트 루프에 제어권을 넘김으로써 백그라운드 태스크 완료 유도
    await asyncio.sleep(0.02)
    
    assert called_event == event
