import json

import pytest

from synapstock.infrastructure.adapters.scraper.naver_ticker_adapter import NaverTickerSearchAdapter


@pytest.fixture
def temp_cache_file(tmp_path):
    cache_data = {
        "LIG디펜스앤에어로스페이스": {
            "name": "LIG디펜스앤에어로스페이스",
            "ticker": "079550",
            "aliases": ["LIG넥스원", "lig넥스원"],
            "is_valid": True
        },
        "삼성전자": {
            "name": "삼성전자",
            "ticker": "005930",
            "aliases": ["삼전"],
            "is_valid": True
        }
    }
    cache_file = tmp_path / "stock_cache.json"
    cache_file.write_text(json.dumps(cache_data, ensure_ascii=False), encoding="utf-8")
    return str(cache_file)

def test_cache_load_and_primary_search(temp_cache_file):
    """정규 사명으로 검색 시 캐시에서 즉시 반환해야 한다."""
    adapter = NaverTickerSearchAdapter(cache_path=temp_cache_file)
    results = adapter.search("LIG디펜스앤에어로스페이스")

    assert len(results) == 1
    assert results[0]["name"] == "LIG디펜스앤에어로스페이스"
    assert results[0]["ticker"] == "079550"

def test_cache_alias_search(temp_cache_file):
    """별칭으로 검색 시 정규 사명을 반환해야 한다."""
    adapter = NaverTickerSearchAdapter(cache_path=temp_cache_file)
    results = adapter.search("LIG넥스원")

    assert len(results) == 1
    assert results[0]["name"] == "LIG디펜스앤에어로스페이스"
    assert results[0]["ticker"] == "079550"

def test_cache_case_insensitive_search(temp_cache_file):
    """대소문자 구분 없이 별칭을 검색해도 정규 사명을 반환해야 한다."""
    adapter = NaverTickerSearchAdapter(cache_path=temp_cache_file)
    results = adapter.search("lig넥스원")

    assert len(results) == 1
    assert results[0]["name"] == "LIG디펜스앤에어로스페이스"
    assert results[0]["ticker"] == "079550"

def test_naver_fallback_normalization(temp_cache_file):
    """네이버 검색 결과가 캐시에 있는 별칭일 경우 정규 사명으로 치환해야 한다."""
    from unittest.mock import patch
    adapter = NaverTickerSearchAdapter(cache_path=temp_cache_file)

    # 캐시에 없는 검색어로 네이버 호출 유도
    query = "LIG"

    mock_response = {
        "result": {
            "items": [
                {"name": "LIG넥스원", "code": "079550"}
            ]
        }
    }

    with patch('requests.get') as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_response

        results = adapter.search(query)
        # 결과는 캐시의 정규 사명인 "LIG디펜스앤에어로스페이스"여야 함
        assert len(results) >= 1
        assert results[0]["name"] == "LIG디펜스앤에어로스페이스"
        assert results[0]["ticker"] == "079550"
