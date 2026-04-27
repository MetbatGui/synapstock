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
        news_folder_id: str | None = None,
    ):
        self.repository = repository
        self.scraper = scraper
        self.drive_adapter = drive_adapter
        self.news_folder_id = news_folder_id
        self._news_cache: dict[str, list[NewsItem]] = {}  # ticker -> items
        self._is_indexed = False

    def _rebuild_index(self):
        """로컬 파일들로부터 메모리 인덱스를 재구성합니다."""
        logger.info("[NewsService] 뉴스 메모리 인덱스 재구성 중...")
        new_cache = {}
        for file_path in self.repository.get_all_batch_files():
            try:
                date_str = file_path.stem.replace("news_", "")
                batch = self.repository.load_batch(date_str)
                if batch:
                    for item in batch.items:
                        if item.ticker:
                            if item.ticker not in new_cache:
                                new_cache[item.ticker] = []
                            new_cache[item.ticker].append(item)
            except Exception as e:
                logger.error(f"[NewsService] 인덱싱 중 오류 ({file_path}): {e}")

        # 날짜순 정렬 (최신순)
        for ticker in new_cache:
            new_cache[ticker].sort(key=lambda x: x.collected_at, reverse=True)

        self._news_cache = new_cache
        self._is_indexed = True
        logger.info(f"[NewsService] 인덱스 재구성 완료 ({len(new_cache)} 종목)")

    async def sync_from_drive(self):
        """구글 드라이브의 뉴스 아카이브와 스마트 동기화를 수행합니다."""
        if not self.drive_adapter or not self.news_folder_id:
            logger.warning("[NewsService] 드라이브 어댑터가 없어 동기화를 건너뜁니다.")
            return

        logger.info("[NewsService] 구글 드라이브 뉴스 동기화 시작...")
        try:
            # StoragePort 인터페이스의 list_files_in_folder 사용
            drive_files = await self.drive_adapter.list_files_in_folder("", folder="news")
            download_count = 0

            for df in drive_files:
                filename = df["name"]
                if not filename.startswith("news_") or not filename.endswith(".json"):
                    continue

                date_str = filename.replace("news_", "").replace(".json", "")

                # 드라이브 수정 시각 (ISO 8601 -> timestamp)
                # 예: 2024-04-23T12:34:56.789Z
                drive_mtime_str = df["modifiedTime"].replace("Z", "+00:00")
                drive_mtime = datetime.fromisoformat(drive_mtime_str).timestamp()

                # 로컬 수정 시각
                local_mtime = self.repository.get_file_mtime(date_str)

                # 드라이브가 더 최신이거나 로컬에 없으면 다운로드
                # (1초 이상의 차이가 있을 때만 업데이트 - 파일 시스템 오차 고려)
                if drive_mtime > local_mtime + 1.0:
                    logger.info(f"[NewsService] 신규/수정 파일 발견: {filename}")
                    content = await self.drive_adapter.get_file(filename, folder="news")
                    if content:
                        # 로컬 저장
                        with open(self.repository._get_file_path(date_str), "wb") as f:
                            f.write(content)
                        download_count += 1

            if download_count > 0 or not self._is_indexed:
                self._rebuild_index()

            logger.info(f"[NewsService] 동기화 완료 ({download_count}개 다운로드)")
        except Exception as e:
            logger.error(f"[NewsService] 동기화 중 오류: {e}", exc_info=True)

    async def add_news_from_url(
        self, url: str, ticker: str | None = None, stock_name: str | None = None
    ) -> NewsItem | None:
        """URL로부터 뉴스를 스크래핑하여 아카이브에 추가하고 동기화합니다."""

        # 1. 스크래핑 수행
        scraped = await self.scraper.scrape(url)
        if not scraped or not scraped.title:
            logger.warning(f"[NewsService] 뉴스 스크래핑 실패: {url}")
            return None

        # 2. 저장 메서드 호출
        return await self.save_news(
            title=scraped.title, url=url, ticker=ticker, stock_name=stock_name
        )

    async def save_news(
        self, title: str, url: str, ticker: str | None = None, stock_name: str | None = None
    ) -> NewsItem | None:
        """이미 확보된 뉴스 정보를 아카이브에 저장하고 동기화합니다."""

        # 1. NewsItem 생성 (저장 시각 및 URL 해시 기준)
        url_hash = hashlib.md5(url.encode()).hexdigest()
        item = NewsItem(
            id=url_hash,
            title=title,
            url=url,
            collected_at=datetime.now(),
            ticker=ticker,
            stock_name=stock_name,
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

            # 메모리 캐시 업데이트
            if ticker:
                if ticker not in self._news_cache:
                    self._news_cache[ticker] = []
                self._news_cache[ticker].insert(0, item)

            if self.drive_adapter and self.news_folder_id:
                await self._sync_to_drive(batch)

            return item

        return None

    async def _sync_to_drive(self, batch: NewsBatch):
        """특정 배치를 구글 드라이브에 업로드합니다."""
        if not self.drive_adapter or not self.news_folder_id:
            return

        filename = f"news_{batch.date}.json"
        content = batch.model_dump_json(indent=2).encode("utf-8")

        try:
            # StoragePort.put_file을 사용하여 업로드
            success = await self.drive_adapter.put_file(
                path=filename,
                data=content,
                folder="news",  # GoogleDriveAdapter에서 news 키워드로 매핑된 폴더 사용
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

    def get_news_for_stock(self, ticker: str) -> list[NewsItem]:
        """특정 종목에 아카이브된 뉴스 목록을 조회합니다 (메모리 캐시 활용)."""
        if not self._is_indexed:
            self._rebuild_index()
        return self._news_cache.get(ticker, [])
