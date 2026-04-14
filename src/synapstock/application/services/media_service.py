"""종목 관련 미디어(리포트, 뉴스) 관리를 담당하는 유즈케이스 레이어."""

from typing import cast

from synapstock.domain.ports import BoardRepositoryPort, StoragePort


class StockMediaService:
    """종목에 종속된 외부 미디어 리소스(PDF, 뉴스 URL)를 관리하는 서비스 클래스입니다. (UseCase - Media)"""

    def __init__(self, repository: BoardRepositoryPort, storage: StoragePort, pdf_dir: str = "data/pdf") -> None:
        """필요한 어댑터들로 서비스를 초기화합니다."""
        self._repository = repository
        self._storage = storage
        self._pdf_dir = pdf_dir

    def add_stock_report(self, board_name: str, ticker: str, file_content: bytes, filename: str) -> bool:
        """종목에 PDF 리포트 파일을 물리적으로 저장하고 보드 데이터에 링크를 기록합니다."""
        # 1. 파일 시스템 저장 (StoragePort 추상화 사용)
        target_path = f"{self._pdf_dir}/{filename}"
        if not self._storage.put_file(target_path, file_content):
            return False

        # 2. 보드 데이터 로드 및 업데이트
        board = self._repository.load(board_name)
        # Node 도메인 모델의 비즈니스 로직 호출 (재귀적 탐색 및 추가)
        success = cast(bool, board.root.find_and_add_report(ticker, target_path))
        if success:
            self._repository.save(board)
        return success

    def remove_stock_report(self, board_name: str, ticker: str, report_path: str) -> bool:
        """종목에서 리포트 파일 링크를 제거합니다. (물리 파일 삭제는 정책에 따라 별도로 처리 가능)"""
        board = self._repository.load(board_name)
        success = cast(bool, board.root.find_and_remove_report(ticker, report_path))
        if success:
            self._repository.save(board)
        return success

    def add_stock_news(self, board_name: str, ticker: str, title: str, date: str, url: str) -> bool:
        """종목에 뉴스 링크 정보를 추가합니다."""
        board = self._repository.load(board_name)
        news_entry = {"title": title, "date": date, "url": url}

        success = cast(bool, board.root.find_and_add_news(ticker, news_entry))
        if success:
            self._repository.save(board)
        return success

    def remove_stock_news(self, board_name: str, ticker: str, url: str) -> bool:
        """종목에서 특정 뉴스 링크를 제거합니다."""
        board = self._repository.load(board_name)
        success = cast(bool, board.root.find_and_remove_news(ticker, url))
        if success:
            self._repository.save(board)
        return success
