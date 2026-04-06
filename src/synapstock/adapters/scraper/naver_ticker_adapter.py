"""Naver 주식 검색 API를 이용한 티커 검색 어댑터."""

import requests
import logging
from typing import List, Dict
from synapstock.domain.ports import TickerSearchPort

logger = logging.getLogger(__name__)

class NaverTickerSearchAdapter(TickerSearchPort):
    """네이버 모바일 주식 검색 API를 사용하여 티커를 검색합니다."""

    BASE_URL = "https://m.stock.naver.com/front-api/search/autoComplete"

    def search(self, query: str) -> List[Dict[str, str]]:
        """네이버 검색 결과를 가져와서 공통 형식(name, ticker)으로 반환합니다."""
        params = {
            "query": query,
            "target": "stock,index,marketindicator,coin,ipo"
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
            "Referer": "https://m.stock.naver.com/search"
        }
        try:
            response = requests.get(self.BASE_URL, params=params, headers=headers, timeout=5)
            response.raise_for_status()
            data = response.json()
            
            items = data.get("result", {}).get("items", [])
            results = []
            for item in items:
                name = item.get("name")
                ticker = item.get("code")
                if name and ticker:
                    # 불필요한 태그 제거 (있는 경우)
                    import re
                    clean_name = re.sub(r'<[^>]*>', '', name)
                    results.append({"name": clean_name, "ticker": ticker})
            return results
        except Exception as e:
            logger.error(f"[NaverTickerSearch] 검색 실패 (query={query}): {e}")
            return []
