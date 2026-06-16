import asyncio
import logging
from typing import Any, Callable, Type

from synapstock.domain.ports import EventBusPort

logger = logging.getLogger(__name__)

class InMemoryEventBusAdapter(EventBusPort):
    """EventBusPort를 구현하는 인메모리 이벤트 버스 어댑터."""

    def __init__(self) -> None:
        self._handlers: dict[Type[Any], list[Callable[..., Any]]] = {}

    def subscribe(self, event_type: Type[Any], handler: Callable[..., Any]) -> None:
        """이벤트 타입에 해당하는 핸들러를 등록합니다."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def publish(self, event: Any) -> None:
        """이벤트를 발행하여 등록된 핸들러들을 호출합니다. 비동기 핸들러는 백그라운드 태스크로 위임됩니다."""
        event_type = type(event)
        handlers = self._handlers.get(event_type, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(handler(event))
                    except RuntimeError:
                        # 이벤트 루프가 실행 중이지 않은 동기 환경일 경우
                        asyncio.run(handler(event))
                else:
                    handler(event)
            except Exception as e:
                handler_name = getattr(handler, "__name__", str(handler))
                logger.error(
                    f"Error handling event {event_type.__name__} in {handler_name}: {e}",
                    exc_info=True
                )
