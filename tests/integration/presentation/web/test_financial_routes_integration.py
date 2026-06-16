import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def client(integration_test_env):
    """DATA_DIR이 임시 경로로 격리된 상태에서 FastAPI 앱 클라이언트를 생성합니다."""
    from evenezer.presentation.web.server import app
    app.router.on_startup = []
    return TestClient(app)


def test_get_quarters(client):
    """GET /api/financials/quarters - 사용 가능한 분기 리스트 조회 검증."""
    response = client.get("/api/financials/quarters?metric=REVENUE")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_get_top_growers(client):
    """GET /api/financials/top-growers - 성장률 상위 종목 조회 검증."""
    # REVENUE 지표에 대한 실적 급성장 종목 순위 요청
    response = client.get("/api/financials/top-growers?metric=REVENUE&top_n=10")
    assert response.status_code == 200
    data = response.json()
    assert "normal" in data
    assert "turnaround" in data
    assert isinstance(data["normal"], list)
    assert isinstance(data["turnaround"], list)


def test_get_consecutive_growers(client):
    """GET /api/financials/consecutive-growers - 연속 성장 종목 조회 검증."""
    # OPERATING_PROFIT(영업이익)이 3분기 연속 성장한 종목 요청
    response = client.get("/api/financials/consecutive-growers?metric=OPERATING_PROFIT&count=3")
    assert response.status_code == 200
    data = response.json()
    assert "normal" in data
    assert "turnaround" in data
    assert isinstance(data["normal"], list)
    assert isinstance(data["turnaround"], list)
