import json
import hashlib
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, ANY

import pytest

from evenezer.application.services.news_service import NewsService
from evenezer.domain.models import ScrapedNews
from evenezer.domain.news.models import NewsBatch, NewsItem


@pytest.fixture
def mock_repo():
    return MagicMock()

@pytest.fixture
def mock_scraper():
    return AsyncMock()

@pytest.fixture
def mock_drive():
    mock = MagicMock()
    mock.get_file = AsyncMock()
    mock.put_file = AsyncMock()
    mock.list_files_in_folder = AsyncMock()
    return mock

@pytest.fixture
def news_service(mock_repo, mock_scraper, mock_drive):
    return NewsService(
        repository=mock_repo,
        scraper=mock_scraper,
        drive_adapter=mock_drive,
        news_folder_id="folder_123"
    )

class TestNewsService:
    @pytest.mark.asyncio
    async def test_save_news_success(self, news_service, mock_repo, mock_drive):
        """뉴스 저장 시 로컬 저장소와 구글 드라이브 동기화가 호출되어야 한다."""
        mock_repo.load_batch.return_value = None # 신규 배치 생성 상황
        mock_repo.save_batch.return_value = True

        item = await news_service.save_news(
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
        # 구글 드라이브 동기화 확인 (뉴스 배치 파일 및 메타데이터 파일 업로드)
        assert mock_drive.put_file.call_count == 2
        today_str = datetime.now().strftime("%Y-%m-%d")
        mock_drive.put_file.assert_any_call(
            path=f"news_{today_str}.json",
            data=ANY,
            folder="news"
        )
        mock_drive.put_file.assert_any_call(
            "news_metadata.json",
            ANY,
            folder="news"
        )

    @pytest.mark.asyncio
    async def test_save_news_duplicate_ignore(self, news_service, mock_repo, mock_drive):
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

        item = await news_service.save_news(
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

    @pytest.mark.asyncio
    async def test_sync_from_drive_with_metadata(self, news_service, mock_drive, mock_repo):
        """메타데이터가 존재할 때 이를 기반으로 신규 파일만 다운로드해야 한다."""
        # 1. 드라이브에 메타데이터와 신규 파일이 있다고 가정
        drive_metadata = {
            "news_2024-04-23.json": "2024-04-23T12:00:00Z",
            "news_2024-04-24.json": "2024-04-24T12:00:00Z"
        }
        mock_drive.get_file.side_effect = [
            json.dumps(drive_metadata).encode("utf-8"), # news_metadata.json
            b"content_2024-04-24" # news_2024-04-24.json (신규)
        ]
        
        # 2. 로컬 상황 모킹
        # 4월 23일은 이미 최신, 24일은 없다고 가정
        mock_repo.get_file_mtime.side_effect = lambda d: 1713873600.0 if d == "2024-04-23" else 0.0
        mock_repo.get_all_batch_files.return_value = [] # 메타데이터 갱신용

        # 3. 실행
        await news_service.sync_from_drive()

        # 4. 검증
        # 메타데이터 확인 시도
        mock_drive.get_file.assert_any_call("news_metadata.json", folder="news")
        
        # 신규 파일만 다운로드 및 저장 시도 (23일은 건너뜀)
        mock_drive.get_file.assert_any_call("news_2024-04-24.json", folder="news")
        mock_repo.save_raw_file.assert_called_once_with(
            "news_2024-04-24.json", b"content_2024-04-24", mtime=ANY
        )
        
        # 로컬 메타데이터 영속화 확인
        mock_repo.save_sync_metadata.assert_called_once()
        # 드라이브 메타데이터 업로드 확인
        mock_drive.put_file.assert_called_with("news_metadata.json", ANY, folder="news")

    @pytest.mark.asyncio
    async def test_merge_batches_basic(self, news_service):
        """두 뉴스 배치를 중복 없이 올바르게 병합해야 한다."""
        item1 = NewsItem(id="hash1", title="뉴스 1", url="http://test.com/1", collected_at=datetime.now())
        item2 = NewsItem(id="hash2", title="뉴스 2", url="http://test.com/2", collected_at=datetime.now())
        item3 = NewsItem(id="hash3", title="뉴스 3", url="http://test.com/3", collected_at=datetime.now())

        batch_local = NewsBatch(date="2026-07-08", items=[item1, item2], last_modified=datetime(2026, 7, 8, 10, 0))
        batch_drive = NewsBatch(date="2026-07-08", items=[item2, item3], last_modified=datetime(2026, 7, 8, 11, 0))

        merged = news_service.merge_batches(batch_local, batch_drive, tombstone=set())

        assert merged is not None
        assert len(merged.items) == 3
        # 중복인 item2는 하나만 존재해야 하며, 1, 2, 3 모두 존재해야 함
        item_ids = {it.id for it in merged.items}
        assert item_ids == {"hash1", "hash2", "hash3"}
        assert merged.last_modified > batch_drive.last_modified

    @pytest.mark.asyncio
    async def test_merge_batches_with_tombstone(self, news_service):
        """Tombstone에 등록된 뉴스 ID는 병합 결과에서 제외되어야 한다."""
        item1 = NewsItem(id="hash1", title="뉴스 1", url="http://test.com/1", collected_at=datetime.now())
        item2 = NewsItem(id="hash2", title="뉴스 2", url="http://test.com/2", collected_at=datetime.now())
        item3 = NewsItem(id="hash3", title="뉴스 3", url="http://test.com/3", collected_at=datetime.now())

        batch_local = NewsBatch(date="2026-07-08", items=[item1, item2], last_modified=datetime(2026, 7, 8, 10, 0))
        batch_drive = NewsBatch(date="2026-07-08", items=[item2, item3], last_modified=datetime(2026, 7, 8, 11, 0))

        # 'hash2'가 Tombstone에 등록되어 삭제 처리된 이력으로 존재함
        tombstone = {"hash2"}
        merged = news_service.merge_batches(batch_local, batch_drive, tombstone=tombstone)

        assert merged is not None
        assert len(merged.items) == 2
        item_ids = {it.id for it in merged.items}
        assert item_ids == {"hash1", "hash3"} # hash2는 제외됨


    @pytest.mark.asyncio
    async def test_merge_batches_basic(self, news_service):
        """두 뉴스 배치를 중복 없이 올바르게 병합해야 한다."""
        item1 = NewsItem(id="hash1", title="뉴스 1", url="http://test.com/1", collected_at=datetime.now())
        item2 = NewsItem(id="hash2", title="뉴스 2", url="http://test.com/2", collected_at=datetime.now())
        item3 = NewsItem(id="hash3", title="뉴스 3", url="http://test.com/3", collected_at=datetime.now())

        batch_local = NewsBatch(date="2026-07-08", items=[item1, item2], last_modified=datetime(2026, 7, 8, 10, 0))
        batch_drive = NewsBatch(date="2026-07-08", items=[item2, item3], last_modified=datetime(2026, 7, 8, 11, 0))

        merged = news_service.merge_batches(batch_local, batch_drive, tombstone=set())

        assert merged is not None
        assert len(merged.items) == 3
        # 중복인 item2는 하나만 존재해야 하며, 1, 2, 3 모두 존재해야 함
        item_ids = {it.id for it in merged.items}
        assert item_ids == {"hash1", "hash2", "hash3"}
        assert merged.last_modified > batch_drive.last_modified

    @pytest.mark.asyncio
    async def test_merge_batches_with_tombstone(self, news_service):
        """Tombstone에 등록된 뉴스 ID는 병합 결과에서 제외되어야 한다."""
        item1 = NewsItem(id="hash1", title="뉴스 1", url="http://test.com/1", collected_at=datetime.now())
        item2 = NewsItem(id="hash2", title="뉴스 2", url="http://test.com/2", collected_at=datetime.now())
        item3 = NewsItem(id="hash3", title="뉴스 3", url="http://test.com/3", collected_at=datetime.now())

        batch_local = NewsBatch(date="2026-07-08", items=[item1, item2], last_modified=datetime(2026, 7, 8, 10, 0))
        batch_drive = NewsBatch(date="2026-07-08", items=[item2, item3], last_modified=datetime(2026, 7, 8, 11, 0))

        # 'hash2'가 Tombstone에 등록되어 삭제 처리된 이력으로 존재함
        tombstone = {"hash2"}
        merged = news_service.merge_batches(batch_local, batch_drive, tombstone=tombstone)

        assert merged is not None
        assert len(merged.items) == 2
        item_ids = {it.id for it in merged.items}
        assert item_ids == {"hash1", "hash3"} # hash2는 제외됨

