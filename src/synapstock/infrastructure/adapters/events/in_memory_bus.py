import asyncio
import logging
from typing import Any, Callable, Type

from synapstock.domain.ports import EventBusPort

logger = logging.getLogger(__name__)

class InMemoryEventBusAdapter(EventBusPort):
    """EventBusPort를 구현하는 인메모리 이벤트 버스 어댑터."""

    def __init__(self, sync_mode: bool = False) -> None:
        self._handlers: dict[Type[Any], list[Callable[..., Any]]] = {}
        self._sync_mode = sync_mode  # 테스트 및 하위 호환성 모드를 위한 동기 완료 강제 옵션

    def subscribe(self, event_type: Type[Any], handler: Callable[..., Any]) -> None:
        """이벤트 타입에 해당하는 핸들러를 등록합니다."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def publish(self, event: Any) -> None:
        """이벤트를 동기적으로 발행합니다. 비동기 핸들러는 백그라운드 태스크로 던집니다."""
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

    async def publish_async(self, event: Any) -> None:
        """이벤트를 비동기적으로 발행합니다. sync_mode=True일 경우 모든 비동기 핸들러 완료를 await 대기합니다."""
        event_type = type(event)
        handlers = self._handlers.get(event_type, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    if self._sync_mode:
                        # 동기식 테스트/호환 환경: 순차 완료 대기
                        await handler(event)
                    else:
                        # 프로덕션 실환경: 백그라운드 태스크 위임 (논블로킹)
                        loop = asyncio.get_running_loop()
                        loop.create_task(handler(event))
                else:
                    handler(event)
            except Exception as e:
                handler_name = getattr(handler, "__name__", str(handler))
                logger.error(
                    f"Error handling event {event_type.__name__} in {handler_name}: {e}",
                    exc_info=True
                )
