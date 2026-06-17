import asyncio
import logging
import inspect
from datetime import datetime
from typing import Any, Callable
from collections.abc import Mapping

from evenezer.domain.ports import EventOutboxPort

logger = logging.getLogger(__name__)

class OutboxWorker:
    """EventOutboxPort에 영속된 이벤트를 순차 소모하여 백그라운드 처리를 완수하는 워커 데몬."""

    def __init__(
        self,
        outbox: EventOutboxPort,
        handlers: Mapping[str, Callable[..., Any]],
        max_retries: int = 5,
        base_delay: float = 2.0,
    ) -> None:
        """OutboxWorker를 초기화합니다.

        Args:
            outbox: 아웃박스 저장소 포트 객체.
            handlers: 이벤트 클래스 이름을 키로, 실행할 핸들러 함수를 값으로 갖는 매핑 객체.
            max_retries: 이벤트별 최대 재시도 횟수 한계값. 기본값은 5.
            base_delay: 지수 백오프의 기준 딜레이 초(seconds). 기본값은 2.0.
        """
        self._outbox = outbox
        self._handlers = handlers
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._task: asyncio.Task | None = None
        self._running = False

    def start(self) -> None:
        """백그라운드 폴링 데몬 루프를 비동기 태스크로 시작합니다."""
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
        """실행 중인 백그라운드 폴링 데몬 루프 태스크를 안전하게 취소하고 종료합니다."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
            logger.info("[OutboxWorker] 백그라운드 폴링 데몬이 종료되었습니다.")

    async def _run_loop(self) -> None:
        """5초마다 대기 중인 이벤트를 감지하여 소모하는 백그라운드 무한 루프입니다."""
        while self._running:
            try:
                await self.process_pending_events()
            except Exception as e:
                logger.error(f"[OutboxWorker] 폴링 루프 실행 오류: {e}", exc_info=True)
            await asyncio.sleep(5.0)

    def _should_retry_now(self, event_item: dict) -> bool:
        """지수 백오프 계산 규칙에 근거하여 지금 재시도를 진행할 타이밍인지 여부를 확인합니다.

        Args:
            event_item: 아웃박스 저장소에서 가져온 이벤트 세부 데이터 딕셔너리.

        Returns:
            대기 시간이 경과하여 즉시 처리가 가능하면 True, 아직 딜레이 시간이 남아 있으면 False.
        """
        retry_count = event_item.get("retry_count", 0)
        if retry_count == 0:
            return True

        updated_at_str = event_item.get("updated_at") or event_item.get("created_at")
        if not updated_at_str:
            return True

        try:
            from datetime import UTC
            updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=UTC)

            # 타임존 인지형(Aware) datetime 연산을 통해 로컬 타임존 간차로 인한 백오프 오작동 버그를 예방합니다.
            elapsed = (datetime.now(UTC) - updated_at).total_seconds()
            # 지수 백오프: base_delay * (2 ** (retry_count - 1))
            delay = self._base_delay * (2 ** (retry_count - 1))
            return elapsed >= delay
        except Exception:
            return True

    def _restore_event(self, event_dict: dict) -> Any:
        """딕셔너리 구조로 저장된 이벤트 데이터를 DomainEvent 인스턴스로 복원합니다.

        Args:
            event_dict: 역직렬화할 원본 이벤트 정보 딕셔너리.

        Returns:
            복원 완료된 DomainEvent 객체 또는 복원 실패 시 원본 event_dict를 그대로 반환.
        """
        try:
            from evenezer.domain.events import DomainEvent
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
                # 영구 실패(Dead Letter) 아카이빙을 위해 complete 대신 fail_permanent를 호출합니다.
                self._outbox.fail_permanent(outbox_id, item.get("last_error") or "Max retries exceeded")
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
