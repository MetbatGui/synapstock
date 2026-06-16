import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.fixture
def client(integration_test_env):
    """DATA_DIR이 임시 경로로 격리된 상태에서 FastAPI 앱 클라이언트를 생성합니다."""
    from evenezer.presentation.web.server import app
    app.router.on_startup = []
    return TestClient(app)


def test_get_local_reports_service_none(client):
    """GET /api/reports/local - report_service가 None일 때 빈 리스트 반환 검증."""
    from evenezer.presentation.web.routes import report_routes
    
    with patch.object(report_routes, "report_service", None):
        response = client.get("/api/reports/local?name=NAVER")
        assert response.status_code == 200
        assert response.json() == []


def test_get_local_reports_success(client):
    """GET /api/reports/local - report_service가 활성화되어 있을 때 리포트 목록 조회 검증."""
    from evenezer.presentation.web.routes import report_routes
    
    mock_report = MagicMock()
    mock_report.filename = "naver_report.pdf"
    mock_report.url = "http://drive/naver"
    mock_report.date = "2026-06-10"
    mock_report.provider = "증권사A"
    mock_report.title = "NAVER 목표주가 상향"
    
    mock_service = MagicMock()
    mock_service.get_reports_by_stock = AsyncMock(return_value=[mock_report])
    
    with patch.object(report_routes, "report_service", mock_service):
        response = client.get("/api/reports/local?name=NAVER")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["filename"] == "naver_report.pdf"
        assert data[0]["title"] == "NAVER 목표주가 상향"


def test_get_report_counts(client):
    """GET /api/reports/counts - 종목별 리포트 수량 집계 조회 검증."""
    from evenezer.presentation.web.routes import report_routes
    
    mock_counts = {"NAVER": 5, "카카오": 3}
    mock_service = MagicMock()
    mock_service.get_report_counts = AsyncMock(return_value=mock_counts)
    
    with patch.object(report_routes, "report_service", mock_service):
        response = client.get("/api/reports/counts")
        assert response.status_code == 200
        assert response.json() == mock_counts


def test_sync_reports_index_success(client):
    """POST /api/reports/sync - 리포트 인덱스 동기화 성공 검증."""
    from evenezer.presentation.web.routes import report_routes
    
    mock_service = MagicMock()
    mock_service.sync_index = AsyncMock(return_value=["list.json", "reports.json"])
    
    with patch.object(report_routes, "report_service", mock_service):
        response = client.post("/api/reports/sync")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "Updated from cloud" in data["message"]


def test_sync_reports_index_service_none(client):
    """POST /api/reports/sync - 서비스 미설정(None) 시 400 에러 반환 검증."""
    from evenezer.presentation.web.routes import report_routes
    
    with patch.object(report_routes, "report_service", None):
        response = client.post("/api/reports/sync")
        assert response.status_code == 400
        assert "Cloud sync not configured" in response.json()["message"]


def test_serve_report_file_found(client, tmp_path):
    """GET /report_files/{filename} - 로컬 PDF 파일 서빙 및 200 OK 검증."""
    from evenezer.presentation.web.routes import report_routes
    
    # 임시 테스트 PDF 파일 생성
    dummy_pdf = tmp_path / "test_report.pdf"
    dummy_pdf.write_bytes(b"%PDF-1.4 dummy pdf content")
    
    mock_service = MagicMock()
    mock_service.get_file_content_path = AsyncMock(return_value=str(dummy_pdf))
    
    with patch.object(report_routes, "report_service", mock_service):
        response = client.get("/report_files/test_report.pdf")
        assert response.status_code == 200
        assert response.content.startswith(b"%PDF-1.4")


def test_serve_report_file_not_found(client):
    """GET /report_files/{filename} - 파일이 존재하지 않을 시 404 에러 반환 검증."""
    from evenezer.presentation.web.routes import report_routes
    
    mock_service = MagicMock()
    mock_service.get_file_content_path = AsyncMock(return_value=None)
    
    with patch.object(report_routes, "report_service", mock_service):
        response = client.get("/report_files/non_existent_report.pdf")
        assert response.status_code == 404
        assert "File not found" in response.json()["message"]
