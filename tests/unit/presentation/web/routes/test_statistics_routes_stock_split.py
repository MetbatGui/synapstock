import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

# 테스트 대상 라우터가 속한 FastAPI 앱 또는 APIRouter 임포트
# presentation/web/server.py 가 존재하므로 이를 참조하거나, APIRouter를 직접 테스트하기 위해 임시 앱을 생성해 테스트함
from fastapi import FastAPI
from synapstock.presentation.web.routes.statistics_routes import router
from synapstock.domain.statistics.models import StockSplit

app = FastAPI()
app.include_router(router)

client = TestClient(app)


@pytest.fixture
def mock_dependencies():
    with patch("synapstock.presentation.web.routes.statistics_routes.stock_split_repo") as mock_repo, \
         patch("synapstock.presentation.web.routes.statistics_routes.stock_split_sync_service") as mock_sync:
        yield mock_repo, mock_sync


def test_get_stock_splits_all(mock_dependencies):
    """GET /api/statistics/stock-splits 호출 시 전체 주식 분할 데이터를 조회하는지 검증."""
    mock_repo, _ = mock_dependencies
    
    # 모의 데이터 설정
    mock_item = StockSplit(
        company_name="삼성전자",
        market="KOSPI",
        disclosure_type="공시",
        base_date="2024-12-12",
        board_resolution_date="2024-12-12",
        receipt_no="20241212801081",
        original_receipt_no=None,
        prev_shares=20520649,
        post_shares=102603245,
        split_ratio=5.0,
        listing_date="2025-02-27",
        general_meeting_date="2024-12-12"
    )
    mock_repo.load_all.return_value = [mock_item]

    response = client.get("/api/statistics/stock-splits")
    
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["items"][0]["company_name"] == "삼성전자"
    mock_repo.load_all.assert_called_once()


def test_get_stock_splits_by_year(mock_dependencies):
    """GET /api/statistics/stock-splits?year=2025 호출 시 특정 연도 데이터를 조회하는지 검증."""
    mock_repo, _ = mock_dependencies
    mock_repo.load_by_year.return_value = []

    response = client.get("/api/statistics/stock-splits?year=2025")
    
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 0
    mock_repo.load_by_year.assert_called_once_with("2025")


def test_get_stock_splits_force_sync(mock_dependencies):
    """GET /api/statistics/stock-splits?force_sync=true 호출 시 동기화 서비스를 트리거하는지 검증."""
    mock_repo, mock_sync = mock_dependencies
    mock_repo.load_all.return_value = []
    mock_sync.sync = AsyncMock(return_value=True)

    response = client.get("/api/statistics/stock-splits?force_sync=true")
    
    assert response.status_code == 200
    mock_sync.sync.assert_called_once()
    mock_repo.load_all.assert_called_once()


def test_sync_stock_splits_endpoint(mock_dependencies):
    """POST /api/statistics/stock-splits/sync 호출 시 수동 동기화를 실행하는지 검증."""
    _, mock_sync = mock_dependencies
    mock_sync.sync = AsyncMock(return_value=True)

    response = client.post("/api/statistics/stock-splits/sync")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    mock_sync.sync.assert_called_once()
