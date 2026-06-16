from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from evenezer.infrastructure.adapters.scraper.httpx_scraper import HttpxNewsScraperAdapter


@pytest.fixture
def scraper():
    return HttpxNewsScraperAdapter(timeout=2)

@pytest.mark.asyncio
async def test_scraper_extracts_og_tags_correctly(scraper):
    """og:title 및 metadata에서 날짜를 올바르게 추출하는지 검증합니다."""

    mock_html = """
    <html>
        <head>
            <meta property="og:title" content="삼성전자 깜짝 실적 발표">
            <meta property="article:published_time" content="2026-04-01T10:00:00+09:00">
        </head>
        <body>본문 내용</body>
    </html>
    """

    # httpx.AsyncClient의 get 메서드를 모킹
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = mock_html

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response

        result = await scraper.scrape("https://example.com/news/123")

        assert result is not None
        assert result.title == "삼성전자 깜짝 실적 발표"
        assert result.date == "2026-04-01"
        assert result.url == "https://example.com/news/123"

@pytest.mark.asyncio
async def test_scraper_fallback_to_title_tag_and_body_date(scraper):
    """og: 태그가 없을 때 title 태그와 본문 날짜 패턴으로 폴백되는지 검증합니다."""

    mock_html = """
    <html>
        <head>
            <title>LIG넥스원, 신규 수주 공시</title>
        </head>
        <body>
            <div>기사 입력: 2026.03.31</div>
            <div>본문 내용 처리 중...</div>
        </body>
    </html>
    """

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = mock_html

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response

        result = await scraper.scrape("https://example.com/news/456")

        assert result is not None
        assert result.title == "LIG넥스원, 신규 수주 공시"
        assert result.date == "2026-03-31" # 본문의 2026.03.31이 2026-03-31로 변환되어야 함

@pytest.mark.asyncio
async def test_scraper_returns_none_on_http_error(scraper):
    """HTTP 응답이 200이 아닐 경우 None을 반환하는지 검증합니다."""

    mock_response = MagicMock()
    mock_response.status_code = 404

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response

        result = await scraper.scrape("https://example.com/not-found")

        assert result is None
