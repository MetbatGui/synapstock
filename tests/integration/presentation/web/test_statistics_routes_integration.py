import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.fixture
def client(integration_test_env):
    """DATA_DIR이 임시 경로로 격리된 상태에서 FastAPI 앱 클라이언트를 생성합니다."""
    from synapstock.presentation.web.server import app
    app.router.on_startup = []
    return TestClient(app)


def test_get_weekly_change(client):
    """GET /api/statistics/weekly-change - 주간 등락률 조회 검증."""
    from synapstock.presentation.web.core.dependencies import weekly_change_service
    
    mock_data = {"date": "2026-06-10", "items": [{"name": "삼성전자", "ratio": 1.5}]}
    with patch.object(weekly_change_service, "get_weekly_change", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_data
        
        response = client.get("/api/statistics/weekly-change?date=2026-06-10")
        assert response.status_code == 200
        assert response.json() == mock_data
        mock_get.assert_called_once_with("2026-06-10", force_sync=False)


def test_get_weekly_change_dates(client):
    """GET /api/statistics/weekly-change/dates - 사용 가능한 주간 등락률 날짜 목록 조회 검증."""
    from synapstock.presentation.web.core.dependencies import weekly_change_service
    
    mock_dates = ["2026-06-03", "2026-06-10"]
    with patch.object(weekly_change_service, "list_available_dates", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = mock_dates
        
        response = client.get("/api/statistics/weekly-change/dates")
        assert response.status_code == 200
        assert response.json() == mock_dates


def test_sync_weekly_change(client):
    """POST /api/statistics/weekly-change/sync - 주간 등락률 수동 동기화 검증."""
    from synapstock.presentation.web.core.dependencies import weekly_change_service
    
    mock_sync_result = MagicMock()
    mock_sync_result.date = "2026-06-10"
    mock_sync_result.items = [{"name": "삼성전자"}]
    
    with patch.object(weekly_change_service, "sync_data", new_callable=AsyncMock) as mock_sync:
        mock_sync.return_value = mock_sync_result
        
        response = client.post("/api/statistics/weekly-change/sync?date=2026-06-10")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["date"] == "2026-06-10"
        assert data["item_count"] == 1


def test_get_daily_ranking(client):
    """GET /api/statistics/daily-ranking - 수급 순위 조회 (실제 엑셀 로딩) 검증."""
    # tests/fixtures/statistics/daily_ranking_20260407.xlsx 파일이 임시 data/statistics/ 에 복사됨
    # 이 파일은 2026-04-07 날짜의 수급 데이터를 포함하고 있으므로, 실제 로딩하여 200을 받는지 검증합니다.
    response = client.get("/api/statistics/daily-ranking?date=2026-04-07&market=KOSPI&subject=FOREIGN")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    # 빈 배열일 수도 있으나 에러 없이 정상 응답하는지 검증
    assert isinstance(data["items"], list)


def test_get_daily_summary(client):
    """GET /api/statistics/daily-summary - 4가지 수급 조합 결과 조회 검증."""
    response = client.get("/api/statistics/daily-summary?date=2026-04-07")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)


def test_get_monthly_summary(client):
    """GET /api/statistics/monthly-summary - 월간 누적 수급 조회 검증."""
    response = client.get("/api/statistics/monthly-summary?month=2026-04")
    assert response.status_code == 200
    data = response.json()
    assert "month" in data
    assert data["month"] == "2026-04"
    assert "KOSPI" in data
    assert "KOSDAQ" in data


def test_get_available_dates(client):
    """GET /api/statistics/available-dates - 수급 순위 가능 날짜 리스트 조회 검증."""
    response = client.get("/api/statistics/available-dates?market=KOSPI&subject=FOREIGN")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    # 복사해온 20260407 파일 덕분에 리스트에 "2026-04-07"이 포함되어야 함
    assert "2026-04-07" in data


def test_sync_statistics(client):
    """POST /api/statistics/sync - 구글 드라이브 수급 데이터 동기화 검증."""
    from synapstock.presentation.web.core.dependencies import statistics_service
    
    with patch.object(statistics_service, "sync_recent_data", new_callable=AsyncMock, return_value=3) as mock_sync:
        response = client.post("/api/statistics/sync")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["synced_count"] == 3
        mock_sync.assert_called_once_with(limit=5)


def test_get_ceiling_report(client):
    """GET /api/statistics/ceiling-report - 상한가 분석 리포트 조회 검증."""
    from synapstock.presentation.web.core.dependencies import statistics_service
    
    mock_report = {"date": "2026-06-10", "items": [{"name": "종목A", "reason": "호재"}]}
    with patch.object(statistics_service, "get_ceiling_analysis", new_callable=AsyncMock, return_value=mock_report) as mock_get:
        response = client.get("/api/statistics/ceiling-report?date=2026-06-10")
        assert response.status_code == 200
        assert response.json() == mock_report


def test_get_ceiling_years(client):
    """GET /api/statistics/ceiling-years - 상한가 가능 연도 조회 검증."""
    from synapstock.presentation.web.core.dependencies import statistics_service
    
    with patch.object(statistics_service, "list_available_ceiling_years", new_callable=AsyncMock, return_value=["2025", "2026"]):
        response = client.get("/api/statistics/ceiling-years")
        assert response.status_code == 200
        assert response.json() == ["2025", "2026"]


def test_get_ceiling_dates(client):
    """GET /api/statistics/ceiling-dates - 상한가 가능 날짜 목록 조회 검증."""
    from synapstock.presentation.web.core.dependencies import statistics_service
    
    with patch.object(statistics_service, "list_available_ceiling_dates", new_callable=AsyncMock, return_value=["2026-06-09", "2026-06-10"]):
        response = client.get("/api/statistics/ceiling-dates?year=2026")
        assert response.status_code == 200
        assert response.json() == ["2026-06-09", "2026-06-10"]


def test_get_new_listing(client):
    """GET /api/statistics/new-listing - 신규상장주 분석 조회 검증."""
    from synapstock.presentation.web.core.dependencies import statistics_service
    
    mock_ipo_data = [{"company_name": "신규A", "listing_date": "2026-06-10"}]
    with patch.object(statistics_service, "get_new_listing_data", new_callable=AsyncMock, return_value=mock_ipo_data) as mock_get:
        response = client.get("/api/statistics/new-listing?year=2026")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["items"] == mock_ipo_data


def test_get_bonus_issue(client):
    """GET /api/statistics/bonus-issue - 무상증자 분석 조회 검증."""
    from synapstock.presentation.web.core.dependencies import statistics_service
    
    mock_bonus_data = [{"company_name": "증자A", "base_date": "2026-06-10"}]
    with patch.object(statistics_service, "get_bonus_issue_data", new_callable=AsyncMock, return_value=mock_bonus_data) as mock_get:
        response = client.get("/api/statistics/bonus-issue")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["items"] == mock_bonus_data
