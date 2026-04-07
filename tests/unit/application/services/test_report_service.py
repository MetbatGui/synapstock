import pytest
import json
from unittest.mock import MagicMock, patch
from pathlib import Path
from synapstock.application.services.report_service import ReportService
from synapstock.domain.models import Report

@pytest.fixture
def mock_cloud_storage():
    return MagicMock()

@pytest.fixture
def mock_local_storage():
    return MagicMock()

@pytest.fixture
def service(mock_cloud_storage, mock_local_storage):
    return ReportService(
        cloud_storage=mock_cloud_storage,
        local_storage=mock_local_storage,
        report_folder_id="folder_id",
        report_dir="data/report"
    )

class TestReportService:
    """ReportService 단위 테스트."""

    def test_get_reports_by_stock_from_list_json(self, service, mock_local_storage):
        """list.json 인덱스에서 종목 리포트를 올바르게 읽어와야 한다.

        Arrange:
            mock_local_storage가 리포트 정보를 담은 list.json 데이터를 반환하도록 설정한다.
        Act:
            service.get_reports_by_stock("삼성전자")를 호출한다.
        Assert:
            반환된 리포트 리스트에 해당 종목 데이터가 포함되어 있는지 확인한다.
        """
        list_data = [
            {"filename": "[삼성전자] 리서치.pdf", "date": "2024-01-01"},
            {"filename": "[SK하이닉스] 실적.pdf", "date": "2024-01-02"}
        ]
        mock_local_storage.get_file.side_effect = lambda path: json.dumps(list_data).encode("utf-8") if path == "list.json" else None
        
        reports = service.get_reports_by_stock("삼성전자")
        
        assert len(reports) == 1
        assert reports[0].stock == "삼성전자"
        assert reports[0].filename == "[삼성전자] 리서치.pdf"

    def test_sync_index_downloads_from_cloud(self, service, mock_cloud_storage, mock_local_storage):
        """sync_index()는 클라우드에서 인덱스를 가져와 로컬에 저장해야 한다.

        Arrange:
            cloud_storage가 인덱스 파일 데이터를 반환하도록 설정한다.
        Act:
            service.sync_index()를 호출한다.
        Assert:
            1. cloud_storage.get_file()이 호출되었는지 확인한다.
            2. local_storage.put_file()이 호출되었는지 확인한다.
        """
        mock_cloud_storage.get_file.return_value = b'{"test": "data"}'
        
        updated = service.sync_index()
        
        assert "list.json" in updated
        assert "reports.json" in updated
        assert mock_cloud_storage.get_file.call_count >= 2
        assert mock_local_storage.put_file.call_count >= 2

    def test_get_file_content_path_triggers_download(self, service, mock_local_storage, mock_cloud_storage):
        """로컬에 파일이 없으면 클라우드에서 다운로드를 시도해야 한다.

        Arrange:
            local_storage.path_exists()가 False를 반환하도록 설정한다.
        Act:
            service.get_file_content_path("new_report.pdf")를 호출한다.
        Assert:
            cloud_storage.download_file()이 호출되었는지 확인한다.
        """
        mock_local_storage.path_exists.return_value = False
        mock_cloud_storage.download_file.return_value = True
        
        path = service.get_file_content_path("new_report.pdf")
        
        assert path == Path("data/report/new_report.pdf")
        mock_cloud_storage.download_file.assert_called_once()
