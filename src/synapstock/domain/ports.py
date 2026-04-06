from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Callable, Optional, Any, List
import pandas as pd
import openpyxl
from synapstock.domain.models import Board, ScrapedNews


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
    def load(self, board_name: str, progress_callback: Callable[[str, float], None] | None = None) -> Board:
        """마인드맵에서 Board를 불러온다.

        Args:
            board_name: 불러올 Board 이름.
            progress_callback: 진행률 업데이트를 위한 콜백 함수 (메시지, 0~1 사이의 값).

        Returns:
            복원된 Board 인스턴스.

        Raises:
            FileNotFoundError: 해당 Board가 존재하지 않을 때.
        """

    @abstractmethod
    def save(self, board: Board, progress_callback: Callable[[str, float], None] | None = None) -> None:
        """Board를 마인드맵 서비스에 반영(저장)한다.

        Args:
            board: 저장할 Board 인스턴스.
            progress_callback: 진행률 업데이트를 위한 콜백 함수 (메시지, 0~1 사이의 값).
        """

    @abstractmethod
    def list_boards(self) -> list[str]:
        """사용 가능한 Board 이름 목록을 반환한다.

        Returns:
            Board 이름 리스트 (정렬됨).
        """

    @abstractmethod
    def sync(self, board: Board, progress_callback: Callable[[str, float], None] | None = None) -> None:
        """Board의 변경사항을 마인드맵 서비스에 동기화한다.

        전체 삭제 후 재생성 대신, 변경된 부분만 업데이트(이동, 수정 등)한다.

        Args:
            board: 동기화할 Board 인스턴스.
            progress_callback: 진행률 업데이트를 위한 콜백 함수 (메시지, 0~1 사이의 값).
        """



class DisclosurePort(ABC):
    """공시 정보 조회를 위한 추상 포트."""

    @abstractmethod
    def get_recent_disclosures(self, ticker: str) -> list[dict]:
        """특정 종목의 최근 공시 목록을 가져온다.

        Args:
            ticker: 종목 코드.

        Returns:
            공시 정보 리스트 (제목, 날짜, 링크 등).
        """

class FinancialDataPort(ABC):
    """재무 데이터 조회를 위한 추상 포트."""

    @abstractmethod
    def get_financial_data(self, company_name: str) -> list[dict]:
        """특정 기업의 분기별 재무 데이터를 가져온다.

        Args:
            company_name: 기업명.

        Returns:
            분기별 재무 정보 리스트 (분기, 수치 등).
        """


class StoragePort(ABC):
    """저장소 추상 포트.
    
    파일의 물리적인 저장/로드를 담당하며, 바이너리 바이트 단위로 작업한다.
    구체적인 객체 변환(DataFrame 등)은 서비스 레이어의 책임이다.
    """

    @abstractmethod
    def path_exists(self, path: str, **kwargs) -> bool:
        """경로 존재 여부를 확인한다."""

    @abstractmethod
    def ensure_directory(self, path: str, **kwargs) -> bool:
        """디렉토리 존재를 보장(없으면 생성)한다."""

    @abstractmethod
    def get_file(self, path: str, **kwargs) -> Optional[bytes]:
        """파일 내용을 바이너리 바이트로 가져온다."""

    @abstractmethod
    def put_file(self, path: str, data: bytes, **kwargs) -> bool:
        """바이트 데이터를 파일로 저장한다."""

    @abstractmethod
    def list_files_in_folder(self, folder_path: str, **kwargs) -> List[dict]:
        """특정 폴더 내의 파일 목록을 조회한다.
        
        Returns:
            List[dict]: [{'id': '...', 'name': '...'}, ...]
        """

    @abstractmethod
    def download_file(self, filename: str, local_path: str, **kwargs) -> bool:
        """파일을 원자적으로(Atomic) 특정 경로에 다운로드한다."""


class TickerSearchPort(ABC):
    """주식 종목 티커 검색을 위한 추상 포트."""

    @abstractmethod
    def search(self, query: str) -> list[dict[str, str]]:
        """검색어에 해당하는 종목 리스트를 반환한다.
        
        Args:
            query: 검색어 (기업명 등)
            
        Returns:
            list[dict[str, str]]: [{'name': '...', 'ticker': '...'}, ...]
        """


class NewsScraperPort(ABC):
    """뉴스 URL에서 메타데이터를 추출하기 위한 추상 포트."""

    @abstractmethod
    async def scrape(self, url: str) -> Optional[ScrapedNews]:
        """URL에서 뉴스 제목과 날짜를 추출한다."""


