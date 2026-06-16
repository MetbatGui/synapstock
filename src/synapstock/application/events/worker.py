import asyncio
import logging
import inspect
from datetime import datetime
from typing import Any, Callable

from synapstock.domain.ports import EventOutboxPort

logger = logging.getLogger(__name__)

class OutboxWorker:
    """EventOutboxPort에 영속된 이벤트를 순차 소모하여 백그라운드 처리를 완수하는 워커 데몬."""

    def __init__(
        self,
        outbox: EventOutboxPort,
        handlers: dict[str, Callable[..., Any]],
        max_retries: int = 5,
        base_delay: float = 2.0,
    ) -> None:
        self._outbox = outbox
        self._handlers = handlers
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._task: asyncio.Task | None = None
        self._running = False

    def start(self) -> None:
        """백그라운드 이벤트 처리 데몬 루프를 시작합니다."""
        if not self._running:
            try:
                loop = asyncio.get_running_loop()
                self._running = True
                self._task = loop.create_task(self._run_loop())
                logger.info("[OutboxWorker] 백그라운드 폴링 데몬이 시작되었습니다.")
            except RuntimeError:
                logger.warning(
                    "[OutboxWorker] 실행 중인 asyncio 이벤트 루프가 없어 백그라운드 데몬을 시작하지 못했습니다. "
                    "테스트 또는 동기식 레거시 동작 중일 수 있습니다."
                )

    def stop(self) -> None:
        """백그라운드 이벤트 처리 데몬 루프를 종료합니다."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
            logger.info("[OutboxWorker] 백그라운드 폴링 데몬이 종료되었습니다.")

    async def _run_loop(self) -> None:
        while self._running:
            try:
                await self.process_pending_events()
            except Exception as e:
                logger.error(f"[OutboxWorker] 폴링 루프 실행 오류: {e}", exc_info=True)
            await asyncio.sleep(5.0)

    def _should_retry_now(self, event_item: dict) -> bool:
        retry_count = event_item.get("retry_count", 0)
        if retry_count == 0:
            return True

        updated_at_str = event_item.get("updated_at") or event_item.get("created_at")
        if not updated_at_str:
            return True

        try:
            updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
            if updated_at.tzinfo is not None:
                updated_at = updated_at.replace(tzinfo=None)

            elapsed = (datetime.now() - updated_at).total_seconds()
            # 지수 백오프: base_delay * (2 ** (retry_count - 1))
            delay = self._base_delay * (2 ** (retry_count - 1))
            return elapsed >= delay
        except Exception:
            return True

    def _restore_event(self, event_dict: dict) -> Any:
        try:
            from synapstock.domain.events import DomainEvent
            return DomainEvent.from_dict(event_dict)
        except Exception as e:
            logger.warning(f"[OutboxWorker] 이벤트 복원 실패 (from_dict): {e}. 원본 딕셔너리를 사용합니다.")
            return event_dict

    async def process_pending_events(self) -> None:
        """PENDING 상태의 이벤트를 순차 로드하여 각각에 연결된 핸들러로 라우팅합니다."""
        pending_events = self._outbox.load_pending()
        for item in pending_events:
            outbox_id = item.get("id")
            if not outbox_id:
                continue

            # 1. 최대 재시도 초과 시 아카이브로 밀어 격리
            retry_count = item.get("retry_count", 0)
            if retry_count >= self._max_retries:
                logger.warning(
                    f"[OutboxWorker] 이벤트 {outbox_id}가 최대 재시도 횟수({self._max_retries}회)를 초과하여 제외(영구 실패) 처리됩니다."
                )
                self._outbox.complete(outbox_id)
                continue

            # 2. 지수 백오프 확인
            if not self._should_retry_now(item):
                continue

            # 3. 이벤트 핸들러 탐색 및 격발
            event_dict = item.get("event", {})
            event_class_name = event_dict.get("event_class", "")
            
            handler = self._handlers.get(event_class_name)
            if not handler:
                logger.warning(f"[OutboxWorker] 이벤트 {event_class_name}에 등록된 핸들러가 없어 완료 처리합니다.")
                self._outbox.complete(outbox_id)
                continue

            try:
                # 도메인 이벤트 객체로 복원 시도
                event_obj = self._restore_event(event_dict)
                
                # 핸들러 실행 (동기/비동기 모두 호환)
                if asyncio.iscoroutinefunction(handler):
                    await handler(event_obj)
                else:
                    handler(event_obj)
                
                # 성공 시 완료 처리
                self._outbox.complete(outbox_id)
                logger.info(f"[OutboxWorker] 이벤트 {outbox_id} ({event_class_name}) 처리 완료.")
            except Exception as e:
                logger.error(
                    f"[OutboxWorker] 이벤트 {outbox_id} ({event_class_name}) 처리 실패 (재시도 예정): {e}",
                    exc_info=True
                )
                self._outbox.fail(outbox_id, str(e))
