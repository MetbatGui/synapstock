"""도메인 포트(인터페이스) 정의."""

from abc import ABC, abstractmethod

from synapstock.domain.models import Board


class BoardRepositoryPort(ABC):
    """Board 저장소 추상 포트.

    구현체는 로컬 파일, DB 등 다양한 방식으로 제공될 수 있다.
    """

    @abstractmethod
    def load(self, name: str) -> Board:
        """name에 해당하는 Board를 불러온다.

        Args:
            name: Board 이름 (파일명 확장자 제외).

        Returns:
            불러온 Board 인스턴스.

        Raises:
            FileNotFoundError: 해당 Board가 존재하지 않을 때.
        """

    @abstractmethod
    def save(self, board: Board) -> None:
        """Board를 저장한다.

        Args:
            board: 저장할 Board 인스턴스.
        """

    @abstractmethod
    def list_boards(self) -> list[str]:
        """저장된 Board 이름 목록을 반환한다.

        Returns:
            Board 이름 리스트 (확장자 제외, 정렬됨).
        """
