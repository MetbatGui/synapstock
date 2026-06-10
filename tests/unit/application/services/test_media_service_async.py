from unittest.mock import AsyncMock, MagicMock

import pytest

from synapstock.application.services.media_service import StockMediaService


@pytest.fixture
def mock_storage():
    storage = AsyncMock()
    storage.put_file.return_value = True
    return storage

@pytest.fixture
def mock_repository():
    repo = MagicMock()
    board = MagicMock()
    repo.load.return_value = board
    board.root.find_and_add_news.return_value = True
    board.add_report_to_stock.return_value = True
    board.remove_report_from_stock.return_value = True
    return repo

@pytest.fixture
def mock_news_service():
    news_svc = AsyncMock()
    return news_svc

@pytest.fixture
def media_service(mock_repository, mock_storage, mock_news_service):
    return StockMediaService(
        repository=mock_repository,
        storage=mock_storage,
        news_service=mock_news_service
    )

@pytest.mark.asyncio
async def test_add_stock_news_async_flow(media_service, mock_news_service):
    """뉴스 추가 로직이 비동기로 올바르게 실행되는지 확인"""
    # Arrange
    board_name = "test_board"
    ticker = "005930"
    title = "테스트 뉴스"
    date = "2024-04-24"
    url = "http://example.com"

    # Act
    success = await media_service.add_stock_news(board_name, ticker, title, date, url)

    # Assert
    assert success is True
    # 뉴스 서비스의 save_news가 비동기로 호출되었는지 확인
    mock_news_service.save_news.assert_awaited_once()

@pytest.mark.asyncio
async def test_add_stock_report_async_storage(media_service, mock_storage):
    """리포트 추가 시 스토리지 저장이 비동기로 호출되는지 확인"""
    # Arrange
    board_name = "test_board"
    ticker = "005930"
    content = b"fake pdf"
    filename = "report.pdf"

    # Act
    success = await media_service.add_stock_report(board_name, ticker, content, filename)

    # Assert
    assert success is True
    # 스토리지의 put_file이 비동기로 호출되었는지 확인
    mock_storage.put_file.assert_awaited_once()
