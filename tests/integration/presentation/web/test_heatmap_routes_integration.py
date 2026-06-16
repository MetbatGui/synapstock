import pytest
import pandas as pd
from fastapi.testclient import TestClient
from unittest.mock import patch

@pytest.fixture
def client(integration_test_env):
    """DATA_DIR이 임시 경로로 격리된 상태에서 FastAPI 앱 클라이언트를 생성합니다."""
    from evenezer.presentation.web.server import app
    app.router.on_startup = []
    return TestClient(app)


def test_get_heatmap_plotly_data(client):
    """GET /api/heatmap/data - Plotly.js Treemap 호환용 히트맵 데이터 생성 검증."""
    # KRX 시세 조회 어댑터를 모킹하여 네트워크 의존성을 제거합니다.
    from evenezer.infrastructure.adapters.heatmap.krx_repository import KrxRepository
    
    # 테마 JSON 파일에 정의된 대표 종목들의 시세 데이터를 모의 생성합니다.
    # 예: NAVER, 카카오, 안랩 등
    mock_df = pd.DataFrame([
        {"Name": "NAVER", "Code": "035420", "Marcap": 20000000000000.0, "ChagesRatio": 1.5},
        {"Name": "카카오", "Code": "035720", "Marcap": 15000000000000.0, "ChagesRatio": -0.8},
        {"Name": "안랩", "Code": "053800", "Marcap": 500000000000.0, "ChagesRatio": 2.3},
        {"Name": "삼성전자", "Code": "005930", "Marcap": 300000000000000.0, "ChagesRatio": 0.5}
    ])
    
    with patch.object(KrxRepository, "fetch_listing", return_value=mock_df) as mock_fetch:
        response = client.get("/api/heatmap/data?show_categories=true&show_stocks=true")
        assert response.status_code == 200
        data = response.json()
        
        # Plotly.js Treemap 최적화 DTO 스키마 확인
        assert "ids" in data
        assert "labels" in data
        assert "parents" in data
        assert "values" in data
        assert "colors" in data
        assert "tickers" in data
        assert "title" in data
        
        assert isinstance(data["ids"], list)
        assert isinstance(data["labels"], list)
        assert len(data["ids"]) > 0
        mock_fetch.assert_called_once()
