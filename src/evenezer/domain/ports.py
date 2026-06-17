from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import Any, Type

from evenezer.domain.models import Board, ScrapedNews, BoardSyncManifest
from evenezer.domain.news.models import NewsBatch
from evenezer.domain.statistics.models import StockSplit, StockSplitManifest




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

    @abstractmethod
    def delete(self, name: str) -> None:
        """이름에 해당하는 Board를 삭제한다.

        Args:
            name: 삭제할 Board 이름.
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
    def get_financial_data(self, company_name: str, metric: str = "매출액", period: str = "분기별") -> list[dict]:
        """특정 기업의 재무 데이터를 가져온다.

        Args:
            company_name: 기업명.
            metric: 조회할 지표 (매출액, 영업이익, 당기순이익 등).
            period: 조회 기간 (분기별, 연간).

        Returns:
            재무 정보 리스트 (분기/연도, 수치 등).
        """


class StoragePort(ABC):
    """저장소 추상 포트.

    파일의 물리적인 저장/로드를 담당하며, 바이너리 바이트 단위로 작업한다.
    구체적인 객체 변환(DataFrame 등)은 서비스 레이어의 책임이다.
    """

    @abstractmethod
    async def path_exists(self, path: str, **kwargs) -> bool:
        """경로 존재 여부를 확인한다."""

    @abstractmethod
    async def ensure_directory(self, path: str, **kwargs) -> bool:
        """디렉토리 존재를 보장(없으면 생성)한다."""

    @abstractmethod
    async def get_file(self, path: str, **kwargs) -> bytes | None:
        """파일 내용을 바이너리 바이트로 가져온다."""

    @abstractmethod
    async def put_file(self, path: str, data: bytes, **kwargs) -> bool:
        """바이트 데이터를 파일로 저장한다."""

    @abstractmethod
    async def list_files_in_folder(self, folder_path: str, **kwargs) -> list[dict]:
        """특정 폴더 내의 파일 목록을 조회한다.

        Returns:
            List[dict]: [{'id': '...', 'name': '...'}, ...]
        """

    @abstractmethod
    async def download_file(self, filename: str, local_path: str, **kwargs) -> bool:
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
    async def scrape(self, url: str) -> ScrapedNews | None:
        """URL에서 뉴스 제목과 날짜를 추출한다."""


class KrxDataPort(ABC):
    """KRX 원천 데이터 수집을 위한 추상 포트."""

    @abstractmethod
    def fetch_net_purchase_data(self, market: str, investor: str, date_str: str) -> bytes:
        """특정 날짜의 투자자별 순매수 데이터(엑셀 바이너리)를 가져온다."""

    @abstractmethod
    def fetch_market_prices(self, market: str, date_str: str) -> list[dict]:
        """특정 날짜의 전종목 시세/대금 데이터를 가져온다."""


class PriceDataPort(ABC):
    """가격 및 신고가 지표 조회를 위한 추상 포트."""

    @abstractmethod
    def get_price_info(self, ticker: str, date_str: str) -> dict | None:
        """특정 종목의 가격 및 신고가 정보를 가져온다."""


class NewsRepositoryPort(ABC):
    """뉴스 데이터 영속성을 위한 추상 포트."""

    @abstractmethod
    def save_batch(self, batch: NewsBatch) -> bool:
        """뉴스 배치를 저장합니다."""

    @abstractmethod
    def load_batch(self, date_str: str) -> NewsBatch | None:
        """특정 날짜의 뉴스 배치를 로드합니다."""

    @abstractmethod
    def list_available_dates(self) -> list[str]:
        """데이터가 존재하는 모든 날짜 목록을 반환합니다."""

    @abstractmethod
    def get_file_mtime(self, date_str: str) -> float:
        """특정 날짜 파일의 수정 시각을 반환합니다."""

    @abstractmethod
    def get_all_batch_files(self) -> list[Path]:
        """모든 뉴스 배치 파일 경로 목록을 반환합니다."""

    @abstractmethod
    def save_raw_file(self, filename: str, content: bytes, mtime: float | None = None) -> None:
        """파일 내용을 저장하고 선택적으로 수정 시각을 설정합니다."""

    @abstractmethod
    def load_sync_metadata(self) -> dict:
        """동기화 메타데이터를 로드합니다."""

    @abstractmethod
    def save_sync_metadata(self, metadata: dict) -> None:
        """동기화 메타데이터를 저장합니다."""


class StockSplitRepositoryPort(ABC):
    """주식 분할(액면분할) 영속성 관리를 위한 추상 포트."""

    @abstractmethod
    def load_all(self) -> list[StockSplit]:
        """모든 주식 분할 이력을 불러옵니다."""

    @abstractmethod
    def load_by_year(self, year: str) -> list[StockSplit]:
        """특정 연도의 주식 분할 이력을 불러옵니다."""

    @abstractmethod
    def load_manifest(self) -> StockSplitManifest | None:
        """로컬 매니페스트 정보를 불러옵니다."""

    @abstractmethod
    def save_manifest(self, manifest: StockSplitManifest) -> None:
        """로컬 매니페스트 정보를 저장합니다."""

    @abstractmethod
    def save_excel_file(self, filename: str, content: bytes) -> None:
        """엑셀 파일 데이터를 로컬 저장소에 저장합니다."""

    @abstractmethod
    def save_manifest_file(self, content: bytes) -> None:
        """매니페스트 JSON 데이터를 로컬 저장소에 저장합니다."""

    @abstractmethod
    def get_file_mtime(self, filename: str) -> float | None:
        """로컬에 다운로드된 파일의 최종 수정 시간(mtime)을 구합니다."""


class BoardSyncManifestRepositoryPort(ABC):
    """통합 보드 및 신규상장주 상태 매니페스트의 영속성 관리를 위한 추상 포트."""

    @abstractmethod
    def load(self) -> BoardSyncManifest:
        """매니페스트 정보를 불러옵니다. 존재하지 않으면 기본 매니페스트 객체를 생성하여 반환합니다."""

    @abstractmethod
    def save(self, manifest: BoardSyncManifest) -> None:
        """매니페스트 정보를 영속성 저장소에 저장합니다."""


class EventBusPort(ABC):
    """이벤트 발행 및 구독을 담당하는 추상 포트."""

    @abstractmethod
    def subscribe(self, event_type: Type[Any], handler: Callable[..., Any]) -> None:
        """이벤트 타입에 해당하는 핸들러를 등록합니다."""
        pass

    @abstractmethod
    def publish(self, event: Any) -> None:
        """이벤트를 발행하여 등록된 핸들러들을 실행합니다."""
        pass

    @abstractmethod
    async def publish_async(self, event: Any) -> None:
        """이벤트를 비동기적으로 발행하고 모든 핸들러의 실행 완료를 대기합니다."""
        pass


class EventOutboxPort(ABC):
    """이벤트 유실 방지 및 비동기 소모를 위한 아웃박스 저장소 추상 포트."""

    @abstractmethod
    def save(self, event: Any) -> str:
        """이벤트를 PENDING 상태로 영속 저장소에 기록하고 고유 ID를 반환합니다."""
        pass

    @abstractmethod
    def load_pending(self) -> list[dict]:
        """처리 대기 중인(PENDING) 이벤트 목록을 조회합니다."""
        pass

    @abstractmethod
    def complete(self, outbox_id: str) -> None:
        """이벤트 처리를 완료하고 아카이브 또는 제거 처리합니다."""
        pass

    @abstractmethod
    def fail(self, outbox_id: str, error_msg: str) -> None:
        """이벤트 처리 실패를 기록하고 재시도 카운트를 갱신합니다."""
        pass

    @abstractmethod
    def fail_permanent(self, outbox_id: str, error_msg: str) -> None:
        """이벤트 처리가 영구적으로 실패했음을 기록하고(재시도 중단) 격리 처리합니다."""
        pass



