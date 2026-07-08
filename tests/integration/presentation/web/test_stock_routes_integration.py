import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.fixture
def client(integration_test_env):
    """DATA_DIR이 임시 경로로 격리된 상태에서 FastAPI 앱 클라이언트를 생성합니다."""
    from evenezer.presentation.web.server import app
    # 테스트 시 startup 이벤트를 비활성화하여 백그라운드 동기화 스레드 실행을 방지합니다.
    app.router.on_startup = []
    return TestClient(app)


def test_get_stock_info_success(client):
    """GET /api/stock/info/{ticker} - 존재하는 종목 조회 성공 검증."""
    # NAVER(035420)는 IT.json(복사되어 theme_IT.json이 됨) 보드에 존재함
    response = client.get("/api/stock/info/035420")
    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "035420"
    assert data["name"] == "NAVER"
    assert "reports" in data
    assert "news" in data
    assert len(data["path"]) > 0
    assert data["path"][0] == "IT"  # 보드 명칭 자체는 JSON 내 "name": "IT" 이므로 IT 임


def test_get_stock_info_not_found(client):
    """GET /api/stock/info/{ticker} - 존재하지 않는 종목 조회 처리 검증."""
    response = client.get("/api/stock/info/999999")
    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "999999"
    assert data["name"] is None
    assert data["reports"] == []
    assert data["news"] == []
    assert data["path"] == []


def test_get_stock_financials(client):
    """GET /api/stock/financials - 재무제표 데이터 조회 검증."""
    # 더존비즈온 종목이 theme_IT.json에 있음
    # 실제 엑셀 파일이 있으면 데이터가 조회될 것임
    response = client.get("/api/stock/financials?name=더존비즈온&metric=매출액&period=분기별")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_search_stock(client):
    """GET /api/stock/search - 종목/티커 검색 검증."""
    # NaverTickerSearchAdapter는 실제로 캐시 파일(stock_cache.json)이나 네이버 검색 API를 모킹 없이 타거나,
    # 여기서는 검색 결과를 통합 테스트하기 위해 mock을 걸거나 빈 결과에 대비함.
    # 안전하게 NaverTickerSearchAdapter의 search 함수만 패치하여 검증합니다.
    from evenezer.presentation.web.core.dependencies import query_service
    
    mock_results = [{"name": "안랩", "ticker": "053800"}]
    with patch.object(query_service._ticker_search, "search", return_value=mock_results) as mock_search:
        response = client.get("/api/stock/search?q=안랩")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert data[0]["name"] == "안랩"
        mock_search.assert_called_once_with("안랩")


def test_get_all_stocks_flat(client):
    """GET /api/stocks/all - 평탄화된 전체 종목 목록 반환 검증."""
    response = client.get("/api/stocks/all")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    # 스키마 확인
    first_item = data[0]
    assert "ticker" in first_item
    assert "name" in first_item
    assert "board" in first_item
    assert "path" in first_item


def test_get_disclosures(client):
    """GET /api/disclosure/{ticker} - 공시 목록 조회 검증."""
    # 외부 DART API 호출을 대체하기 위해 query_service.get_disclosures 모킹
    from evenezer.presentation.web.core.dependencies import query_service
    
    mock_disclosures = [
        {"rcpNo": "202601010001", "title": "정기공시", "date": "2026-01-01"}
    ]
    with patch.object(query_service, "get_disclosures", return_value=mock_disclosures) as mock_get:
        response = client.get("/api/disclosure/035420")
        assert response.status_code == 200
        data = response.json()
        assert data == mock_disclosures
        mock_get.assert_called_once_with("035420")


def test_scrape_news_success(client):
    """GET /api/news/scrape - 뉴스 URL 성공 스크랩 검증."""
    from evenezer.presentation.web.core.dependencies import news_service
    
    mock_scraped = MagicMock()
    mock_scraped.title = "테스트 뉴스 제목"
    mock_scraped.date = "2026-06-10"
    
    with patch.object(news_service.scraper, "scrape", new_callable=AsyncMock) as mock_scrape:
        mock_scrape.return_value = mock_scraped
        
        response = client.get("/api/news/scrape?url=https://news.naver.com/main/read.nhn?articleId=123")
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "테스트 뉴스 제목"
        assert data["date"] == "2026-06-10"
        assert data["url"] == "https://news.naver.com/main/read.nhn?articleId=123"


def test_scrape_news_invalid_url(client):
    """GET /api/news/scrape - 잘못된 URL 형식 요청 시 400 반환 검증."""
    response = client.get("/api/news/scrape?url=invalid_url")
    assert response.status_code == 400
    assert "Invalid URL format" in response.json()["message"]


def test_add_and_delete_stock_news(client):
    """POST /api/stock/news/add 및 DELETE /api/stock/news/delete 통합 검증."""
    # NAVER(035420) 종목이 theme_IT.json에 있고 여기에 뉴스를 추가/삭제해본다.
    news_params = {
        "board": "theme_IT",
        "ticker": "035420",
        "title": "NAVER 신규 서비스 출시",
        "date": "2026-06-10",
        "url": "https://news.naver.com/test1"
    }
    
    # 1. 뉴스 추가
    response_add = client.post(
        f"/api/stock/news/add?board={news_params['board']}&ticker={news_params['ticker']}"
        f"&title={news_params['title']}&date={news_params['date']}&url={news_params['url']}"
    )
    assert response_add.status_code == 200
    assert response_add.json() == {"status": "success"}
    
    # 2. 추가된 뉴스 조회 검사
    response_info = client.get(f"/api/stock/info/{news_params['ticker']}")
    assert response_info.status_code == 200
    info_data = response_info.json()
    assert any(n["url"] == news_params["url"] for n in info_data["news"])
    
    # 3. 뉴스 삭제
    response_del = client.delete(
        f"/api/stock/news/delete?board={news_params['board']}&ticker={news_params['ticker']}&url={news_params['url']}"
    )
    assert response_del.status_code == 200
    assert response_del.json() == {"status": "success"}
    
    # 4. 실제 뉴스 목록에서 완전히 지워졌는지 최종 검증
    response_info_after = client.get(f"/api/stock/info/{news_params['ticker']}")
    assert response_info_after.status_code == 200
    info_data_after = response_info_after.json()
    assert not any(n["url"] == news_params["url"] for n in info_data_after["news"])


def test_get_stock_info_refresh_trigger(client):
    """GET /api/stock/info/{ticker}?refresh=true - 강제 드라이브 동기화 및 캐시 만료 유도 검증."""
    from evenezer.presentation.web.core.dependencies import news_service
    
    with patch.object(news_service, "sync_from_drive", new_callable=AsyncMock) as mock_sync, \
         patch.object(news_service, "invalidate_cache") as mock_invalidate:
         
        response = client.get("/api/stock/info/035420?refresh=true")
        assert response.status_code == 200
        
        # refresh=true 일 때 동기화 및 캐시 무효화가 작동해야 함
        mock_sync.assert_called_once()
        mock_invalidate.assert_called_once()
