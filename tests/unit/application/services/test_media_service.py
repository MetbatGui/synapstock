from unittest.mock import AsyncMock, MagicMock

import pytest

from synapstock.application.services.media_service import StockMediaService
from synapstock.domain.models import Board, Stock


@pytest.fixture
def mock_repo():
    mock = MagicMock()
    return mock


@pytest.fixture
def mock_storage():
    mock = MagicMock()
    mock.put_file = AsyncMock()
    return mock


@pytest.fixture
def mock_news_service():
    mock = MagicMock()
    mock.save_news = AsyncMock()
    return mock


@pytest.fixture
def service(mock_repo, mock_storage, mock_news_service):
    return StockMediaService(
        repository=mock_repo,
        storage=mock_storage,
        news_service=mock_news_service,
        pdf_dir="data/pdf"
    )


class TestStockMediaService:
    """StockMediaService 단위 테스트."""

    @pytest.mark.asyncio
    async def test_add_stock_report_success(self, service, mock_repo, mock_storage):
        """리포트 파일을 저장하고 보드 데이터에 추가해야 한다."""
        board = Board(name="테스트")
        board.add_stock_to_node("테스트", Stock(name="삼성전자", ticker="005930"))
        mock_repo.load.return_value = board
        mock_storage.put_file.return_value = True

        success = await service.add_stock_report("테스트", "005930", b"PDF_CONTENT", "report.pdf")

        assert success is True
        assert "data/pdf/report.pdf" in board.nodes["테스트"].stocks[0].reports
        mock_storage.put_file.assert_called_once()
        mock_repo.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_stock_news_success(self, service, mock_repo, mock_news_service):
        """뉴스 정보를 중앙 아카이브에 저장해야 한다."""
        board = Board(name="테스트")
        board.add_stock_to_node("테스트", Stock(name="삼성전자", ticker="005930"))
        mock_repo.load.return_value = board

        success = await service.add_stock_news("테스트", "005930", "기사제목", "2024-01-01", "http://news/1", stock_name="삼성전자")

        assert success is True
        mock_news_service.save_news.assert_called_once_with(
            title="기사제목",
            url="http://news/1",
            ticker="005930",
            stock_name="삼성전자"
        )
