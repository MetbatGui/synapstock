import pytest
import hashlib
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime
from synapstock.application.services.news_service import NewsService
from synapstock.domain.news.models import NewsBatch, NewsItem
from synapstock.domain.models import ScrapedNews

@pytest.fixture
def mock_repo():
    return MagicMock()

@pytest.fixture
def mock_scraper():
    return AsyncMock()

@pytest.fixture
def mock_drive():
    return MagicMock()

@pytest.fixture
def news_service(mock_repo, mock_scraper, mock_drive):
    return NewsService(
        repository=mock_repo,
        scraper=mock_scraper,
        drive_adapter=mock_drive,
        news_folder_id="folder_123"
    )

class TestNewsService:
    def test_save_news_success(self, news_service, mock_repo, mock_drive):
        """뉴스 저장 시 로컬 저장소와 구글 드라이브 동기화가 호출되어야 한다."""
        mock_repo.load_batch.return_value = None # 신규 배치 생성 상황
        mock_repo.save_batch.return_value = True
        
        item = news_service.save_news(
            title="테스트 뉴스",
            url="http://example.com/1",
            ticker="005930",
            stock_name="삼성전자"
        )
        
        assert item is not None
        assert item.title == "테스트 뉴스"
        assert item.ticker == "005930"
        
        # 로컬 저장 확인
        mock_repo.save_batch.assert_called_once()
        # 구글 드라이브 동기화 확인
        mock_drive.put_file.assert_called_once()

    def test_save_news_duplicate_ignore(self, news_service, mock_repo, mock_drive):
        """이미 존재하는 뉴스는 중복 저장하지 않아야 한다."""
        url = "http://example.com/1"
        url_hash = hashlib.md5(url.encode()).hexdigest()
        today = datetime.now().strftime("%Y-%m-%d")
        existing_item = NewsItem(
            id=url_hash,
            title="기존 뉴스",
            url=url,
            collected_at=datetime.now()
        )
        mock_repo.load_batch.return_value = NewsBatch(date=today, items=[existing_item])
        
        item = news_service.save_news(
            title="중복 뉴스",
            url="http://example.com/1"
        )
        
        assert item.id == existing_item.id
        mock_repo.save_batch.assert_not_called()
        mock_drive.put_file.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_news_from_url_success(self, news_service, mock_scraper, mock_repo):
        """URL로부터 스크래핑 후 저장이 성공적으로 이루어져야 한다."""
        mock_scraper.scrape.return_value = ScrapedNews(
            title="스크래핑된 뉴스",
            date="2024-04-23",
            url="http://example.com/2"
        )
        mock_repo.load_batch.return_value = None
        mock_repo.save_batch.return_value = True
        
        item = await news_service.add_news_from_url("http://example.com/2")
        
        assert item is not None
        assert item.title == "스크래핑된 뉴스"
        mock_scraper.scrape.assert_called_once_with("http://example.com/2")
