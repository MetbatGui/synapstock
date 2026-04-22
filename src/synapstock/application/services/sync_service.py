"""외부 마인드맵과의 데이터 동기화를 담당하는 유즈케이스 레이어."""

from collections.abc import Callable

from synapstock.domain.models import Board
from synapstock.domain.ports import MindmapPort, TickerSearchPort


class BoardSyncService:
    """마인드맵(Miro 등)과 보드 데이터 간의 동기화 및 정규화 작업을 수행하는 서비스 클래스입니다. (UseCase - Sync)"""

    def __init__(self, mindmap: MindmapPort, ticker_search: TickerSearchPort) -> None:
        """필요한 어댑터들로 서비스를 초기화합니다."""
        self._mindmap = mindmap
        self._ticker_search = ticker_search

    def sync_with_miro(self, board: Board, progress_callback: Callable[[str, float], None] | None = None) -> None:
        """티커 정규화를 먼저 수행한 후 보드 데이터를 Miro 마인드맵과 최종 동기화합니다."""
        if progress_callback:
            progress_callback("보드 데이터 티커 정규화 중...", 0.0)

        # 모든 노드를 순회하며 티커가 없는 종목 보정 (비즈니스 정책)
        self._normalize_board_tickers(board, progress_callback)

        self._mindmap.sync(board, progress_callback=progress_callback)

    def _normalize_board_tickers(self, board: Board, progress_callback: Callable[[str, float], None] | None) -> None:
        """보드 내의 모든 종목에 대해 티커 매칭 및 정규화를 시도합니다."""

        def normalize_node(n):
            for s in n.stocks:
                # 1. 티커가 부실한 경우 검색하여 채워줌
                current_ticker_valid = s.ticker and s.ticker.isdigit() and len(s.ticker) == 6

                # 검색을 통한 티커 확인 및 사명 변경 감지
                results = self._ticker_search.search(s.name)
                if results:
                    best_match = results[0]
                    new_ticker = best_match["ticker"]
                    new_name = best_match["name"]

                    # 티커가 없었던 경우 업데이트
                    if not current_ticker_valid:
                        s.ticker = new_ticker
                        if progress_callback:
                            progress_callback(f"티커 매칭 완료: {s.name} -> {s.ticker}", 0.0)

                    # 티커가 일치하는데 이름이 다른 경우 (사명 변경 감지)
                    elif s.ticker == new_ticker and s.name != new_name:
                        if progress_callback:
                            progress_callback(f"사명 변경 감지: {s.name} -> {new_name}", 0.0)

                        # 기존 이름을 별칭으로 격하
                        if s.name not in s.aliases:
                            s.aliases.append(s.name)

                        # 신규 사명으로 교체
                        s.name = new_name

            for child in n.nodes:
                normalize_node(child)

        if board.root:
            normalize_node(board.root)

    def sync(self, board: Board, progress_callback: Callable[[str, float], None] | None = None) -> None:
        """정규화 없이 보드 변경사항을 마인드맵에 즉시 동기화합니다."""
        self._mindmap.sync(board, progress_callback=progress_callback)

    def save_to_mindmap(self, board: Board, progress_callback: Callable[[str, float], None] | None = None) -> None:
        """보드 데이터를 마인드맵의 물리적 요소로 생성/저장합니다."""
        self._mindmap.save(board, progress_callback=progress_callback)
