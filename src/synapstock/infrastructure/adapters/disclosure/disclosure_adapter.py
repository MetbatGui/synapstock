import logging
import re
from datetime import datetime, timedelta
from typing import cast

import requests
from bs4 import BeautifulSoup, Tag

from synapstock.domain.ports import DisclosurePort

logger = logging.getLogger(__name__)


class DartDisclosureAdapter(DisclosurePort):
    """DART(전자공시시스템) 상세검색을 활용한 공시 정보 어댑터입니다."""

    def __init__(self):
        """DART 어댑터를 초기화하고 필요한 HTTP 헤더를 설정합니다."""
        self.base_url = "https://dart.fss.or.kr"
        self.search_url = f"{self.base_url}/dsab007/detailSearch.ax"
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/145.0.0.0 Safari/537.36"
            ),
            "Referer": f"{self.base_url}/dsab007/main.do",
            "Origin": self.base_url,
            "X-Requested-With": "XMLHttpRequest",
        }

    def get_recent_disclosures(self, ticker: str) -> list[dict]:
        """DART 상세검색 POST 요청을 통해 최근 1년치 공시를 가져옵니다.

        Args:
            ticker: 종목 티커 심볼.

        Returns:
            list[dict]: 공시 항목 목록 (최대 10건).
        """
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")

        # 사용자가 제공한 페이로드 기반 구성
        payload = {
            "currentPage": "1",
            "maxResults": "15",
            "maxLinks": "10",
            "sort": "date",
            "series": "desc",
            "textCrpNm": ticker,  # 종목 코드로 검색
            "startDate": start_date,
            "endDate": end_date,
            "decadeType": "finalReport",
            "recent": "businessNm",
            "corporationType": "all",
            "closingAccountsMonth": "all",
            "reportNamePopYn": "N",
            "autoSearch": "N",
            "option": "corp",
        }

        try:
            response = requests.post(self.search_url, data=payload, headers=self.headers, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")
            rows = soup.select("table tbody tr")

            results = []
            for row in rows:
                cols = row.select("td")
                if len(cols) < 5:
                    continue

                # 공시 제목 및 rcpNo 추출
                link_tag = cols[2].select_one("a")
                if not isinstance(link_tag, Tag):
                    continue

                title = link_tag.get_text(strip=True)
                # onclick="openDisclosure('20240320000123')" 형태에서 rcpNo 추출
                onclick = str(link_tag.get("onclick", ""))
                rcp_match = re.search(r"'(20[0-9]{12})'", onclick)
                rcp_no = rcp_match.group(1) if rcp_match else ""

                date = cols[4].get_text(strip=True)

                if rcp_no:
                    results.append(
                        {
                            "title": title,
                            "date": date,
                            "rcpNo": rcp_no,
                            "url": f"{self.base_url}/dsaf001/main.do?rcpNo={rcp_no}",
                        }
                    )

            return cast(list[dict], results[:10])  # 최신 10건만 반환

        except Exception as e:
            logger.error(f"[DART ERROR] Failed to fetch disclosures for {ticker}: {e}")
            return []
