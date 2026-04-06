"""외부 마인드맵과의 데이터 동기화를 담당하는 유즈케이스 레이어."""

from typing import Callable, Optional
from synapstock.domain.models import Board
from synapstock.domain.ports import MindmapPort, TickerSearchPort

class BoardSyncService:
    """마인드맵(Miro 등)과 보드 데이터 간의 동기화 및 정규화 작업을 수행하는 서비스 클래스입니다. (UseCase - Sync)"""

    def __init__(self, mindmap: MindmapPort, ticker_search: TickerSearchPort) -> None:
        """필요한 어댑터들로 서비스를 초기화합니다."""
        self._mindmap = mindmap
        self._ticker_search = ticker_search

    def sync_with_miro(self, board: Board, progress_callback: Optional[Callable[[str, float], None]] = None) -> None:
        """티커 정규화를 먼저 수행한 후 보드 데이터를 Miro 마인드맵과 최종 동기화합니다."""
        if progress_callback:
            progress_callback("보드 데이터 티커 정규화 중...", 0.0)
        
        # 모든 노드를 순회하며 티커가 없는 종목 보정 (비즈니스 정책)
        self._normalize_board_tickers(board, progress_callback)
            
        self._mindmap.sync(board, progress_callback=progress_callback)

    def _normalize_board_tickers(self, board: Board, progress_callback: Optional[Callable[[str, float], None]]) -> None:
        """보드 내의 모든 종목에 대해 티커 매칭 및 정규화를 시도합니다."""
        def normalize_node(n):
            for s in n.stocks:
                # 티커가 부실한 경우(6자리 숫자가 아님) 검색 시도
                if not s.ticker or not s.ticker.isdigit() or len(s.ticker) != 6:
                    results = self._ticker_search.search(s.name)
                    if results:
                        s.ticker = results[0]["ticker"]
                        if progress_callback:
                            progress_callback(f"티커 매칭 완료: {s.name} -> {s.ticker}", 0.0)
            for child in n.nodes:
                normalize_node(child)
        
        if board.root:
            normalize_node(board.root)

    def sync(self, board: Board, progress_callback: Optional[Callable[[str, float], None]] = None) -> None:
        """정규화 없이 보드 변경사항을 마인드맵에 즉시 동기화합니다."""
        self._mindmap.sync(board, progress_callback=progress_callback)

    def save_to_mindmap(self, board: Board, progress_callback: Optional[Callable[[str, float], None]] = None) -> None:
        """보드 데이터를 마인드맵의 물리적 요소로 생성/저장합니다."""
        self._mindmap.save(board, progress_callback=progress_callback)
