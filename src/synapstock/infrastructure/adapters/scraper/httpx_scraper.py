"""HTTPX 기반 뉴스 스크래퍼 어댑터."""

import logging
import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup, Tag

from synapstock.domain.models import ScrapedNews
from synapstock.domain.ports import NewsScraperPort

logger = logging.getLogger(__name__)


class HttpxNewsScraperAdapter(NewsScraperPort):
    """httpx와 BeautifulSoup을 사용하여 뉴스 메타데이터를 추출하는 어댑터."""

    def __init__(self, timeout: int = 10):
        """초기화.

        Args:
            timeout (int): HTTP 요청 타임아웃 (초). 기본값 10.
        """
        self.timeout = timeout
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }

    async def scrape(self, url: str) -> ScrapedNews | None:
        """URL에서 뉴스 제목과 날짜를 추출한다.

        Args:
            url (str): 스크래핑할 뉴스 URL.

        Returns:
            Optional[ScrapedNews]: 추출된 뉴스 정보, 실패 시 None.
        """
        try:
            async with httpx.AsyncClient(headers=self.headers, timeout=self.timeout, follow_redirects=True) as client:
                response = await client.get(url)

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
