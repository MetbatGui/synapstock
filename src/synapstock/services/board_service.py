"""Board 서비스 레이어."""

from synapstock.domain.models import Board
from synapstock.domain.ports import MindmapPort


class BoardService:
    """Board 도메인 유즈케이스를 담당하는 서비스.

    MindmapPort를 통해 어댑터(로컬 폴더, Miro 등)와 통신한다.
    어댑터 구현체를 교체해도 이 서비스 코드는 변경되지 않는다.

    Attributes:
        _mindmap: 마인드맵 서비스 포트 구현체.
    """

    def __init__(self, mindmap: MindmapPort) -> None:
        self._mindmap = mindmap

    def load(self, board_name: str) -> Board:
        """마인드맵에서 Board를 불러온다.

        Args:
            board_name: 불러올 Board 이름.

        Returns:
            복원된 Board 인스턴스 (트리 구조).

        Raises:
            FileNotFoundError: 해당 Board가 존재하지 않을 때.
        """
        return self._mindmap.load(board_name)

    def save(self, board: Board) -> None:
        """Board를 마인드맵에 반영한다.

        Args:
            board: 저장할 Board 인스턴스.
        """
        self._mindmap.save(board)

    def list_boards(self) -> list[str]:
        """사용 가능한 Board 이름 목록을 반환한다.

        Returns:
            Board 이름 리스트 (정렬됨).
        """
        return self._mindmap.list_boards()
