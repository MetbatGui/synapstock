import pytest
from unittest.mock import MagicMock
from synapstock.services.media_service import StockMediaService
from synapstock.domain.models import Board, Node, Stock

@pytest.fixture
def mock_repo():
    return MagicMock()

@pytest.fixture
def mock_storage():
    return MagicMock()

@pytest.fixture
def service(mock_repo, mock_storage):
    return StockMediaService(
        repository=mock_repo,
        storage=mock_storage,
        pdf_dir="data/pdf"
    )

class TestStockMediaService:
    """StockMediaService 단위 테스트."""

    def test_add_stock_report_success(self, service, mock_repo, mock_storage):
        """리포트 파일을 저장하고 보드 데이터에 추가해야 한다."""
        root = Node(name="Root", depth=0)
        root.stocks.append(Stock(name="삼성전자", ticker="005930"))
        board = Board(name="테스트", root=root)
        mock_repo.load.return_value = board
        mock_storage.put_file.return_value = True
        
        success = service.add_stock_report("테스트", "005930", b"PDF_CONTENT", "report.pdf")
        
        assert success is True
        assert "data/pdf/report.pdf" in root.stocks[0].reports
        mock_storage.put_file.assert_called_once()
        mock_repo.save.assert_called_once()

    def test_add_stock_news_success(self, service, mock_repo):
        """뉴스 정보를 보드 데이터에 추가해야 한다."""
        root = Node(name="Root", depth=0)
        root.stocks.append(Stock(name="삼성전자", ticker="005930"))
        board = Board(name="테스트", root=root)
        mock_repo.load.return_value = board
        
        success = service.add_stock_news("테스트", "005930", "기사제목", "2024-01-01", "http://news/1")
        
        assert success is True
        assert len(root.stocks[0].news) == 1
        assert root.stocks[0].news[0]["title"] == "기사제목"
        mock_repo.save.assert_called_once()
