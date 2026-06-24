"""보드 구조 변경 및 명령 서비스를 담당하는 유즈케이스 레이어."""

from typing import Any, cast

from evenezer.domain.events import (
    BatchStocksDeletedFromBoard,
    BoardCreated,
    BoardDeleted,
    NodeAdded,
    NodeDeleted,
    StockAddedToBoard,
    StockDeletedFromBoard,
)
from evenezer.domain.models import Board, Stock
from evenezer.domain.ports import BoardRepositoryPort, EventBusPort


class BoardCommandService:
    """보드의 구조적 변경(추가/삭제) 작업을 수행하는 서비스 클래스입니다. (CQRS - Command)"""

    def __init__(
        self,
        repository: BoardRepositoryPort,
        event_bus: EventBusPort | None = None,
        sync_service: Any = None,
    ) -> None:
        """필요한 퍼시스턴스 어댑터 및 이벤트 버스로 초기화합니다. 하위 호환성을 위해 sync_service도 수용합니다."""
        self._repository = repository
        if event_bus is None:
            from evenezer.infrastructure.adapters.events.in_memory_bus import InMemoryEventBusAdapter
            # 레거시 폴백 환경에서는 동기식 순차 실행을 기대하므로 sync_mode=True로 인메모리 버스를 초기화합니다.
            self._event_bus = InMemoryEventBusAdapter(sync_mode=True)
            if sync_service is not None:
                self._bind_legacy_sync_service(sync_service)
        else:
            self._event_bus = event_bus

    def _bind_legacy_sync_service(self, sync_service: Any) -> None:
        """기존 sync_service를 이벤트 버스에 바인딩하여 하위 호환성을 보장합니다."""
        self._event_bus.subscribe(
            BoardCreated,
            lambda ev: sync_service.update_local_manifest(ev.board_id, deleted=False)
        )
        self._event_bus.subscribe(
            BoardDeleted,
            lambda ev: sync_service.update_local_manifest(ev.board_id, deleted=True)
        )
        self._event_bus.subscribe(
            NodeAdded,
            lambda ev: sync_service.update_local_manifest(ev.board_id, deleted=False)
        )
        self._event_bus.subscribe(
            NodeDeleted,
            lambda ev: sync_service.update_local_manifest(ev.board_id, deleted=False)
        )

        async def handle_stock_added(ev: StockAddedToBoard):
            sync_service.update_local_manifest(ev.board_id, deleted=False)
            await sync_service.handle_stock_addition_trigger(
                ev.ticker, ev.board_id, ev.parent_path.split("/")
            )
            await sync_service.sync_with_drive()

        self._event_bus.subscribe(StockAddedToBoard, handle_stock_added)

        async def handle_stock_deleted(ev: StockDeletedFromBoard):
            sync_service.update_local_manifest(ev.board_id, deleted=False)
            await sync_service.handle_stock_deletion_trigger(ev.ticker, ev.board_id)
            await sync_service.sync_with_drive()

        self._event_bus.subscribe(StockDeletedFromBoard, handle_stock_deleted)

        async def handle_batch_stocks_deleted(ev: BatchStocksDeletedFromBoard):
            sync_service.update_local_manifest(ev.board_id, deleted=False)
            await sync_service.handle_batch_stock_deletion_trigger(ev.tickers, ev.board_id)
            await sync_service.sync_with_drive()

        self._event_bus.subscribe(BatchStocksDeletedFromBoard, handle_batch_stocks_deleted)

    def _resolve_node_path(self, board: Board, name_or_path: str) -> str | None:
        """단순 노드 이름 또는 경로를 입력받아 board.nodes 내의 실제 절대 경로 키로 해소합니다."""
        if name_or_path in board.nodes:
            return name_or_path
        # 이름 매칭 시도 (가장 depth가 얕은 경로를 우선 반환)
        candidates = [path for path, node in board.nodes.items() if node.name == name_or_path]
        if candidates:
            candidates.sort(key=lambda p: len(p.split("/")))
            return candidates[0]
        return None

    def add_node(self, board_name: str, parent_name: str, new_node_name: str) -> bool:
        """특정 부모 노드 아래에 하위 노드를 추가합니다."""
        board = self._repository.load(board_name)
        parent_path = self._resolve_node_path(board, parent_name)
        if not parent_path:
            return False

        success = cast(bool, board.add_node(parent_path, new_node_name))
        if success:
            self._repository.save(board)
            for event in board.pull_events():
                self._event_bus.publish(event)
        return success

    async def add_stock(self, board_name: str, parent_name: str, stock_name: str, ticker: str) -> bool:
        """특정 부모 노드 아래에 새 종목을 추가합니다."""
        board = self._repository.load(board_name)
        parent_path = self._resolve_node_path(board, parent_name)
        if not parent_path:
            return False

        success = cast(bool, board.add_stock_to_node(parent_path, Stock(name=stock_name, ticker=ticker)))
        if success:
            self._repository.save(board)
            for event in board.pull_events():
                await self._event_bus.publish_async(event)
        return success

    def delete_node(self, board_name: str, node_name: str) -> bool:
        """특정 노드를 삭제하고 구조를 재조립합니다."""
        board = self._repository.load(board_name)
        node_path = self._resolve_node_path(board, node_name)
        if not node_path:
            return False

        success = cast(bool, board.delete_node(node_path))
        if success:
            self._repository.save(board)
            for event in board.pull_events():
                self._event_bus.publish(event)
        return success

    async def delete_stock(self, board_name: str, ticker: str) -> bool:
        """보드 내에서 특정 종목(티커 기준)을 찾아 삭제합니다."""
        board = self._repository.load(board_name)
        success = cast(bool, board.delete_stock(ticker))
        if success:
            self._repository.save(board)
            for event in board.pull_events():
                await self._event_bus.publish_async(event)
        return success

    def create_board(self, name: str) -> bool:
        """새로운 빈 보드를 생성합니다. 이미 존재하는 경우 생성을 거부합니다."""
        try:
            if name in self._repository.list_boards():
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"[BoardCommandService] 보드 생성 거부: '{name}' 보드가 이미 존재합니다.")
                return False
            board = Board(id=name, name=name)
            self._repository.save(board)
            self._event_bus.publish(BoardCreated(board_id=name, name=name))
            return True
        except Exception:
            return False

    def delete_board(self, name: str) -> bool:
        """보드 전체를 삭제합니다."""
        try:
            self._repository.delete(name)
            self._event_bus.publish(BoardDeleted(board_id=name))
            return True
        except Exception:
            return False

    async def batch_ignore_stocks(self, board_name: str, tickers: list[str]) -> bool:
        """가상 보드에서 여러 종목을 일괄 제외하고 이벤트를 발행합니다."""
        if not tickers:
            return True

        board = self._repository.load(board_name)
        any_success = False

        for ticker in tickers:
            if board.delete_stock(ticker):
                any_success = True

        if any_success:
            self._repository.save(board)
            # 개별 StockDeleted 이벤트를 디스패치하지 않고 일괄 처리를 위해 비운 뒤 배치 이벤트를 발행
            board.pull_events()
            await self._event_bus.publish_async(BatchStocksDeletedFromBoard(board_id=board_name, tickers=tickers))

        return any_success
