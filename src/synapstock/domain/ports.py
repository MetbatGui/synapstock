"""도메인 포트(인터페이스) 정의."""

from abc import ABC, abstractmethod
from pathlib import Path

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


class MindmapPort(ABC):
    """마인드맵 서비스 추상 포트.

    로컬 폴더, Miro 등 실제 마인드맵 서비스와 연동하는 어댑터가 구현한다.
    BoardRepositoryPort와 시그니처가 유사하나, 단순 스냅샷 저장이 아닌
    마인드맵 서비스의 구조(노드 생성·연결 등)를 반영하는 것이 목적이다.
    """

    @abstractmethod
    def load(self, board_name: str) -> Board:
        """마인드맵에서 board_name에 해당하는 Board를 읽어온다.

        Args:
            board_name: Board 이름.

        Returns:
            복원된 Board 인스턴스.

        Raises:
            FileNotFoundError: 해당 Board가 존재하지 않을 때.
        """

    @abstractmethod
    def save(self, board: Board) -> None:
        """Board를 마인드맵 서비스에 반영(저장)한다.

        Args:
            board: 저장할 Board 인스턴스.
        """

    @abstractmethod
    def list_boards(self) -> list[str]:
        """사용 가능한 Board 이름 목록을 반환한다.

        Returns:
            Board 이름 리스트 (정렬됨).
        """
