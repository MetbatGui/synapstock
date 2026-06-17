import asyncio
import logging
from typing import Any, Callable, Type

from evenezer.domain.ports import EventBusPort

logger = logging.getLogger(__name__)

class InMemoryEventBusAdapter(EventBusPort):
    """EventBusPort를 구현하는 인메모리 이벤트 버스 어댑터입니다.

    메모리 내부에서 발생한 이벤트를 구독자(핸들러)들에게 즉시 라우팅합니다.
    """

    def __init__(self, sync_mode: bool = False) -> None:
        """InMemoryEventBusAdapter를 초기화합니다.

        Args:
            sync_mode: True일 경우 테스트 및 하위 호환성을 위해 모든 비동기 핸들러를 순차적으로 완료 대기(await)합니다.
        """
        self._handlers: dict[Type[Any], list[Callable[..., Any]]] = {}
        self._sync_mode = sync_mode  # 테스트 및 하위 호환성 모드를 위한 동기 완료 강제 옵션

    def subscribe(self, event_type: Type[Any], handler: Callable[..., Any]) -> None:
        """이벤트 타입에 해당하는 핸들러를 등록합니다.

        Args:
            event_type: 구독할 이벤트 클래스 타입.
            handler: 이벤트 발생 시 실행할 콜백 함수 (동기 및 비동기 코루틴 지원).
        """
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def publish(self, event: Any) -> None:
        """이벤트를 동기적으로 발행합니다.

        비동기 핸들러는 백그라운드 태스크(create_task)로 등록하며, 활성화된 이벤트 루프가
        없다면 일시적으로 신규 루프를 구동하여 처리합니다.

        Args:
            event: 발행할 이벤트 인스턴스 객체.
        """
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
        """이벤트를 비동기적으로 발행합니다.

        sync_mode가 활성화되어 있을 경우 비동기 핸들러가 모두 완료될 때까지 대기(await)합니다.

        Args:
            event: 발행할 이벤트 인스턴스 객체.
        """
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
