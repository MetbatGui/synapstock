"""Naver 주식 검색 API를 이용한 티커 검색 어댑터."""

import logging

import requests

from synapstock.domain.ports import TickerSearchPort

logger = logging.getLogger(__name__)

class NaverTickerSearchAdapter(TickerSearchPort):
    """네이버 모바일 주식 검색 API를 사용하여 티커를 검색합니다.
    
    로컬 stock_cache.json이 존재하는 경우 별칭 동기화 기능을 수행합니다.
    """

    BASE_URL = "https://m.stock.naver.com/front-api/search/autoComplete"

    def __init__(self, cache_path: str | None = None) -> None:
        """어댑터를 초기화하고 캐시가 지정된 경우 로드합니다."""
        self.cache_path = cache_path
        self._name_map: dict[str, dict[str, str]] = {}
        self._load_cache()

    def _load_cache(self) -> None:
        """stock_cache.json을 읽어 이름/별칭 -> {name, ticker} 매핑을 구축합니다."""
        if not self.cache_path:
            return
            
        import json
        from pathlib import Path
        path = Path(self.cache_path)
        if not path.exists():
            return
            
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
                
            for primary_name, info in data.items():
                if not isinstance(info, dict):
                    continue
                
                ticker = info.get("ticker", "")
                if not ticker:
                    continue
                
                target_info = {"name": primary_name, "ticker": ticker}
                
                # 정규 이름 매핑 (소문자화하여 저장)
                self._name_map[primary_name.lower()] = target_info
                
                # 별칭 매핑
                for alias in info.get("aliases", []):
                    self._name_map[alias.lower()] = target_info
        except Exception as e:
            logger.warning(f"[NaverTickerSearch] 캐시 로드 실패: {e}")

    def search(self, query: str) -> list[dict[str, str]]:
        """로컬 캐시를 우선 검색한 후 네이버 검색 결과를 가져옵니다."""
        results: list[dict[str, str]] = []
        low_query = query.lower().strip()
        
        # 1. 로컬 캐시(별칭 포함)에서 정확히 일치하는 항목 확인
        if low_query in self._name_map:
            results.append(self._name_map[low_query])
            return results  # 정확히 일치하는 캐시가 있으면 즉시 반환

        # 2. 네이버 API 검색
        params = {
            "query": query,
            "target": "stock,index,marketindicator,coin,ipo"
        }
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/145.0.0.0 Safari/537.36"
            ),
            "Referer": "https://m.stock.naver.com/search"
        }
        try:
            response = requests.get(self.BASE_URL, params=params, headers=headers, timeout=5)
            response.raise_for_status()
            data = response.json()

            items = data.get("result", {}).get("items", [])
            for item in items:
                name = item.get("name")
                ticker = item.get("code")
                if name and ticker:
                    import re
                    clean_name = re.sub(r'<[^>]*>', '', name)
                    
                    # 네이버 결과도 로컬 캐시를 거쳐 이름 정규화 시도
                    if clean_name.lower() in self._name_map:
                        normalized = self._name_map[clean_name.lower()]
                        # 중복 방지
                        if not any(r["ticker"] == normalized["ticker"] for r in results):
                            results.append(normalized)
                    else:
                        results.append({"name": clean_name, "ticker": ticker})
            return results
        except Exception as e:
            logger.error(f"[NaverTickerSearch] 검색 실패 (query={query}): {e}")
            return results
