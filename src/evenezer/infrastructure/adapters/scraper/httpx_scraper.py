"""HTTPX 기반 뉴스 스크래퍼 어댑터."""

import logging
import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup, Tag

from evenezer.domain.models import ScrapedNews
from evenezer.domain.ports import NewsScraperPort

logger = logging.getLogger(__name__)


class HttpxNewsScraperAdapter(NewsScraperPort):
    """httpx와 BeautifulSoup 라이브러리를 사용하여 웹 문서로부터 뉴스 제목 및 발행일을 추출하는 어댑터입니다."""

    def __init__(self, timeout: int = 10):
        """HttpxNewsScraperAdapter를 초기화합니다.

        Args:
            timeout: HTTP 요청 시의 타임아웃 제한 시간 (초). 기본값은 10.
        """
        self.timeout = timeout
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }
        # Connection Pooling을 위해 단일 AsyncClient 인스턴스를 유지합니다.
        self._client = httpx.AsyncClient(headers=self.headers, timeout=self.timeout, follow_redirects=True)

    async def close(self) -> None:
        """클라이언트 리소스를 안전하게 닫고 해제합니다."""
        await self._client.aclose()

    async def scrape(self, url: str) -> ScrapedNews | None:
        """지정된 뉴스 URL에 비동기 GET 요청을 보내 정보를 파싱하고 스크랩된 데이터를 반환합니다.

        오픈 그래프 메타데이터(og:title)와 일반 타이틀 태그로부터 뉴스 제목을 조회하며,
        메타 속성(published_time, date 등) 및 본문 정규식 매칭을 통해 뉴스 발행일을 추출합니다.
        날짜 파싱 실패 시 오늘 날짜를 폴백 값으로 부여합니다.

        Args:
            url: 스크래핑 대상 뉴스의 웹 URL 주소.

        Returns:
            추출 완료된 ScrapedNews 도메인 인스턴스. 스크래핑 실패 또는 응답 불능 시 None.
        """
        try:
            response = await self._client.get(url)

            if response.status_code != 200:
                return None


            # 응답 인코딩 처리
            html = response.text
            soup = BeautifulSoup(html, "html.parser")

            # 1. 제목 추출
            title = ""
            og_title = soup.find("meta", property="og:title")
            if isinstance(og_title, Tag):
                title = str(og_title.get("content", ""))
            if not title:
                title_tag = soup.find("title")
                if title_tag:
                    title = title_tag.get_text().strip()

            # 2. 날짜 추출
            date_str = ""
            date_tags = [
                ("meta", {"property": "article:published_time"}),
                ("meta", {"property": "og:pubdate"}),
                ("meta", {"name": "pubdate"}),
                ("meta", {"name": "date"}),
            ]

            for tag_name, attrs in date_tags:
                tag = soup.find(tag_name, attrs)
                if isinstance(tag, Tag):
                    content = str(tag.get("content", ""))
                    if content:
                        date_match = re.search(r"(\d{4}[.\-/]\d{2}[.\-/]\d{2})", content)
                        if date_match:
                            date_str = date_match.group(1).replace(".", "-").replace("/", "-")
                            break

            # 본문에서 날짜 패턴 검색 폴백 (YYYY.MM.DD 등)
            if not date_str:
                match = re.search(r"(\d{4}[.\-/]\d{2}[.\-/]\d{2})", html)
                if match:
                    date_str = match.group(1).replace(".", "-").replace("/", "-")
                else:
                    date_str = datetime.now().strftime("%Y-%m-%d")

            return ScrapedNews(title=title, date=date_str, url=url)

        except Exception as e:
            logger.error(f"[HttpxNewsScraperAdapter] Error scraping {url}: {e}")
            return None
