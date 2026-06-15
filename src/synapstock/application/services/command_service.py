"""보드 구조 변경 및 명령 서비스를 담당하는 유즈케이스 레이어."""

from typing import cast

from synapstock.application.services.board_file_sync_service import BoardFileSyncService
from synapstock.domain.models import Board, Stock
from synapstock.domain.ports import BoardRepositoryPort


class BoardCommandService:
    """보드의 구조적 변경(추가/삭제) 작업을 수행하는 서비스 클래스입니다. (CQRS - Command)"""

    def __init__(
        self, repository: BoardRepositoryPort, sync_service: BoardFileSyncService | None = None
    ) -> None:
        """필요한 퍼시스턴스 어댑터 및 동기화 서비스로 초기화합니다."""
        self._repository = repository
        self._sync_service = sync_service

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
            if self._sync_service:
                self._sync_service.update_local_manifest(board_name, deleted=False)
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
            if self._sync_service:
                self._sync_service.update_local_manifest(board_name, deleted=False)
                # 신규상장주 상태 자동 감지 훅 호출
                await self._sync_service.handle_stock_addition_trigger(ticker, board_name, parent_path.split("/"))
                # 구글 드라이브 동기화 강제 트리거
                await self._sync_service.sync_with_drive()
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
            if self._sync_service:
                self._sync_service.update_local_manifest(board_name, deleted=False)
        return success

    async def delete_stock(self, board_name: str, ticker: str) -> bool:
        """보드 내에서 특정 종목(티커 기준)을 찾아 삭제합니다."""
        board = self._repository.load(board_name)
        success = cast(bool, board.delete_stock(ticker))
        if success:
            self._repository.save(board)
            if self._sync_service:
                self._sync_service.update_local_manifest(board_name, deleted=False)
                # 가상보드 삭제 감지 훅 호출
                await self._sync_service.handle_stock_deletion_trigger(ticker, board_name)
                # 구글 드라이브 동기화 강제 트리거
                await self._sync_service.sync_with_drive()
        return success

    def create_board(self, name: str) -> bool:
        """새로운 빈 보드를 생성합니다."""
        try:
            from synapstock.domain.models import Board, Node
            # 루트 노드 추가는 Board 도메인 내부 model_validator에서 처리하므로 dict만 생성
            board = Board(id=name, name=name)
            self._repository.save(board)
            if self._sync_service:
                self._sync_service.update_local_manifest(name, deleted=False)
            return True
        except Exception:
            return False

    def delete_board(self, name: str) -> bool:
        """보드 전체를 삭제합니다."""
        try:
            self._repository.delete(name)
            if self._sync_service:
                self._sync_service.update_local_manifest(name, deleted=True)
            return True
        except Exception:
            return False

    async def batch_ignore_stocks(self, board_name: str, tickers: list[str]) -> bool:
        """가상 보드에서 여러 종목을 일괄 제거하고 매니페스트 상의 상태를 IGNORED로 업데이트합니다."""
        if not tickers:
            return True

        board = self._repository.load(board_name)
        any_success = False

        for ticker in tickers:
            if board.delete_stock(ticker):
                any_success = True

        if any_success:
            self._repository.save(board)
            if self._sync_service:
                self._sync_service.update_local_manifest(board_name, deleted=False)
                # 가상보드 일괄 삭제 감지 훅 호출
                await self._sync_service.handle_batch_stock_deletion_trigger(tickers, board_name)
                # 구글 드라이브 동기화 강제 트리거
                await self._sync_service.sync_with_drive()
                
        return any_success

