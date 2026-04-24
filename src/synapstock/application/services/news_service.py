import hashlib
import logging
from datetime import datetime

from synapstock.domain.news.models import NewsBatch, NewsItem
from synapstock.domain.ports import NewsScraperPort, StoragePort
from synapstock.infrastructure.adapters.local.news_repo import LocalNewsRepository

logger = logging.getLogger(__name__)

class NewsService:
    """뉴스 데이터의 수집, 저장 및 동기화를 총괄하는 서비스."""

    def __init__(
        self,
        repository: LocalNewsRepository,
        scraper: NewsScraperPort,
        drive_adapter: StoragePort | None = None,
        news_folder_id: str | None = None
    ):
        self.repository = repository
        self.scraper = scraper
        self.drive_adapter = drive_adapter
        self.news_folder_id = news_folder_id

    async def add_news_from_url(self, url: str, ticker: str | None = None, stock_name: str | None = None) -> NewsItem | None:
        """URL로부터 뉴스를 스크래핑하여 아카이브에 추가하고 동기화합니다."""

        # 1. 스크래핑 수행
        scraped = await self.scraper.scrape(url)
        if not scraped or not scraped.title:
            logger.warning(f"[NewsService] 뉴스 스크래핑 실패: {url}")
            return None

        # 2. 저장 메서드 호출
        return self.save_news(
            title=scraped.title,
            url=url,
            ticker=ticker,
            stock_name=stock_name
        )

    def save_news(self, title: str, url: str, ticker: str | None = None, stock_name: str | None = None) -> NewsItem | None:
        """이미 확보된 뉴스 정보를 아카이브에 저장하고 동기화합니다."""

        # 1. NewsItem 생성 (저장 시각 및 URL 해시 기준)
        url_hash = hashlib.md5(url.encode()).hexdigest()
        item = NewsItem(
            id=url_hash,
            title=title,
            url=url,
            collected_at=datetime.now(),
            ticker=ticker,
            stock_name=stock_name
        )

        # 2. 날짜별 배치 관리 (저장일 기준 파티셔닝)
        today_str = datetime.now().strftime("%Y-%m-%d")
        batch = self.repository.load_batch(today_str)
        if not batch:
            batch = NewsBatch(date=today_str, items=[])

        # 중복 체크
        if any(it.id == item.id for it in batch.items):
            logger.info(f"[NewsService] 이미 존재하는 뉴스입니다 (ID: {item.id})")
            return next(it for it in batch.items if it.id == item.id)

        # 3. 저장 및 동기화
        batch.items.append(item)
        if self.repository.save_batch(batch):
            logger.info(f"[NewsService] 뉴스 아카이브 저장 완료: {item.title}")

            if self.drive_adapter and self.news_folder_id:
                self._sync_to_drive(batch)

            return item

        return None

    def _sync_to_drive(self, batch: NewsBatch):
        """특정 배치를 구글 드라이브에 업로드합니다."""
        if not self.drive_adapter or not self.news_folder_id:
            return

        filename = f"news_{batch.date}.json"
        content = batch.model_dump_json(indent=2).encode("utf-8")

        try:
            # StoragePort.put_file을 사용하여 업로드
            success = self.drive_adapter.put_file(
                path=filename,
                data=content,
                folder="news" # GoogleDriveAdapter에서 news 키워드로 매핑된 폴더 사용
            )
            if success:
                logger.info(f"[NewsService] 구글 드라이브 동기화 성공: {filename}")
            else:
                logger.error(f"[NewsService] 구글 드라이브 동기화 실패: {filename}")
        except Exception as e:
            logger.error(f"[NewsService] 구글 드라이브 동기화 중 오류: {e}")

    def get_news_by_date(self, date_str: str) -> NewsBatch | None:
        """특정 날짜의 뉴스 배치를 조회합니다."""
        return self.repository.load_batch(date_str)
