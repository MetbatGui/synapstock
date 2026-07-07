import hashlib
import json
import logging
from datetime import UTC, datetime

from evenezer.domain.news.models import NewsBatch, NewsItem
from evenezer.domain.ports import NewsRepositoryPort, NewsScraperPort, StoragePort

logger = logging.getLogger(__name__)


class NewsService:
    """뉴스 데이터의 수집, 저장 및 동기화를 총괄하는 서비스."""

    def __init__(
        self,
        repository: NewsRepositoryPort,
        scraper: NewsScraperPort,
        drive_adapter: StoragePort | None = None,
        news_folder_id: str | None = None,
    ):
        """NewsService를 초기화합니다.

        Args:
            repository: 뉴스 데이터 영속성 관리를 위한 포트.
            scraper: 뉴스 URL 파싱 및 정보 추출을 위한 스크래퍼 포트.
            drive_adapter: 구글 드라이브 동기화를 수행할 저장소 어댑터 포트 (선택 사항).
            news_folder_id: 구글 드라이브의 뉴스 폴더 식별자 ID (선택 사항).
        """
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
        """메타데이터 파일을 대조하여 구글 드라이브와 스마트 동기화를 수행합니다."""
        if not self.drive_adapter or not self.news_folder_id:
            logger.warning("[NewsService] 드라이브 어댑터가 없어 동기화를 건너뜁니다.")
            return

        logger.info("[NewsService] 구글 드라이브 뉴스 동기화 시작 (메타데이터 대조)...")
        try:
            # 1. 드라이브에서 메타데이터 파일 가져오기
            metadata_content = await self.drive_adapter.get_file("news_metadata.json", folder="news")

            # 메타데이터가 없으면 드라이브 파일 목록을 직접 조회하여 생성 시도 (폴백)
            if not metadata_content:
                logger.info("[NewsService] 드라이브에 메타데이터가 없습니다. 파일 목록을 직접 조회합니다.")
                drive_files = await self.drive_adapter.list_files_in_folder("", folder="news")
                drive_metadata = {
                    f["name"]: f["modifiedTime"]
                    for f in drive_files if f["name"].startswith("news_") and f["name"].endswith(".json")
                }
            else:
                drive_metadata = json.loads(metadata_content.decode("utf-8"))

            download_count = 0
            for filename, drive_mtime_str in drive_metadata.items():
                if filename == "news_metadata.json":
                    continue

                date_str = filename.replace("news_", "").replace(".json", "")

                # 시각 변환 및 로컬 비교 (개선 B)
                drive_mtime = self._parse_drive_mtime(drive_mtime_str)
                local_mtime = self.repository.get_file_mtime(date_str)

                # 드라이브가 더 최신이거나 로컬에 없으면 다운로드
                if drive_mtime > local_mtime + 1.0:
                    logger.info(f"[NewsService] 다운로드 대상 발견: {filename}")
                    content = await self.drive_adapter.get_file(filename, folder="news")

                    if content:
                        # Repository를 통한 저장 및 시각 설정 (개선 A)
                        self.repository.save_raw_file(filename, content, mtime=drive_mtime)
                        logger.info(f"[NewsService] 다운로드 완료: {filename}")
                        download_count += 1
                    else:
                        logger.error(f"[NewsService] 파일 내용 로드 실패: {filename}")

            if download_count > 0 or not self._is_indexed:
                self._rebuild_index()

            # 로컬 메타데이터 최신화 및 필요시 드라이브 업로드 (동기화 보장)
            await self._update_local_metadata(drive_metadata)

            logger.info(f"[NewsService] 동기화 프로세스 종료 ({download_count}개 업데이트)")
        except Exception as e:
            logger.error(f"[NewsService] 동기화 중 치명적 오류: {e}", exc_info=True)

    def _parse_drive_mtime(self, mtime_str: str) -> float:
        """드라이브의 ISO 시각 문자열을 timestamp로 변환합니다.

        Args:
            mtime_str: 구글 드라이브 파일의 ISO 8601 시각 형식 문자열.

        Returns:
            Epoch 타임스탬프 실수(float) 값.
        """
        return datetime.fromisoformat(mtime_str.replace("Z", "+00:00")).timestamp()

    async def _update_local_metadata(self, drive_metadata: dict):
        """로컬 뉴스 파일 상태를 기반으로 메타데이터를 갱신하고 드라이브에 업로드합니다.

        Args:
            drive_metadata: 이전 원격/로컬 메타데이터 통합본 딕셔너리.
        """
        local_metadata = {}
        for file_path in self.repository.get_all_batch_files():
            filename = file_path.name
            mtime = datetime.fromtimestamp(file_path.stat().st_mtime, tz=UTC)
            local_metadata[filename] = mtime.isoformat().replace("+00:00", "Z")

        # 드라이브 정보와 로컬 정보를 합치되, 로컬 정보를 우선 반영 (최신화 및 누락 방지)
        combined_metadata = {**drive_metadata, **local_metadata}

        # Repository를 통해 메타데이터 영속화 (개선 C)
        self.repository.save_sync_metadata(combined_metadata)

        if self.drive_adapter:
            content = json.dumps(combined_metadata, indent=2).encode("utf-8")
            await self.drive_adapter.put_file("news_metadata.json", content, folder="news")

    async def add_news_from_url(
        self, url: str, ticker: str | None = None, stock_name: str | None = None
    ) -> NewsItem | None:
        """URL로부터 뉴스를 스크래핑하여 아카이브에 추가하고 동기화합니다.

        Args:
            url: 스크래핑할 뉴스의 웹 링크 URL.
            ticker: 연관 주식 종목 코드 (6자리) (선택 사항).
            stock_name: 연관 주식 종목명 (선택 사항).

        Returns:
            성공적으로 생성 및 저장된 NewsItem 객체. 실패 시 None.
        """
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
        """이미 확보된 뉴스 정보를 아카이브에 저장하고 동기화합니다.

        Args:
            title: 저장할 뉴스 제목.
            url: 뉴스 원본 링크 URL (ID 해시값 계산용).
            ticker: 연관 주식 종목 코드 (6자리) (선택 사항).
            stock_name: 연관 주식 종목명 (선택 사항).

        Returns:
            저장 완료된 NewsItem 객체. 이미 존재할 경우 기존 객체를 반환하며, 실패 시 None.
        """
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
        """특정 뉴스 배치를 구글 드라이브에 업로드합니다.

        Args:
            batch: 업로드할 일별 뉴스 배치(NewsBatch) 객체.
        """
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
                # 로컬 메타데이터 정보를 갱신하고 구글 드라이브에 업로드
                current_metadata = self.repository.load_sync_metadata()
                await self._update_local_metadata(current_metadata)
            else:
                logger.error(f"[NewsService] 구글 드라이브 동기화 실패: {filename}")
        except Exception as e:
            logger.error(f"[NewsService] 구글 드라이브 동기화 중 오류: {e}")

    def get_news_by_date(self, date_str: str) -> NewsBatch | None:
        """특정 날짜의 뉴스 배치를 조회합니다.

        Args:
            date_str: 조회 대상 일자 문자열 (YYYY-MM-DD).

        Returns:
            해당 날짜의 뉴스 배치(NewsBatch) 객체. 없으면 None.
        """
        return self.repository.load_batch(date_str)

    def get_news_for_stock(self, ticker: str) -> list[NewsItem]:
        """특정 종목에 아카이브된 뉴스 목록을 메모리 캐시를 기반으로 조회합니다.

        Args:
            ticker: 조회 대상 주식 종목 코드 (6자리).

        Returns:
            해당 종목과 연관된 뉴스 목록 리스트.
        """
        if not self._is_indexed:
            self._rebuild_index()
        return self._news_cache.get(ticker, [])
