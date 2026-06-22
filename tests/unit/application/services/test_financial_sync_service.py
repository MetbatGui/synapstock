import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from evenezer.application.services.financial_sync_service import FinancialSyncService
from evenezer.domain.financials.models import FinancialMetric


@pytest.fixture
def mock_drive_adapter():
    adapter = MagicMock()
    # get_file_metadata 모의
    adapter.get_file_metadata = AsyncMock(return_value={
        "id": "file_123",
        "name": "재무제표.xlsx",
        "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "modifiedTime": "2026-06-22T06:00:00Z"
    })
    # get_file_by_id 모의
    adapter.get_file_by_id = AsyncMock(return_value=b"mock excel data")
    return adapter


@pytest.fixture
def mock_repository():
    repo = MagicMock()
    return repo


@pytest.mark.asyncio
async def test_sync_no_drive_adapter_returns_false():
    service = FinancialSyncService(None, "file_123", Path("data"), None)
    success = await service.sync()
    assert success is False


@pytest.mark.asyncio
async def test_sync_no_file_id_returns_false(mock_drive_adapter):
    service = FinancialSyncService(mock_drive_adapter, None, Path("data"), None)
    success = await service.sync()
    assert success is False


@pytest.mark.asyncio
@patch("os.path.getmtime")
@patch("os.utime")
@patch("builtins.open", new_callable=MagicMock)
@patch("pathlib.Path.exists")
@patch("pathlib.Path.mkdir")
async def test_sync_successful(mock_mkdir, mock_exists, mock_open, mock_utime, mock_getmtime, mock_drive_adapter, mock_repository):
    # 파일이 존재하지 않는 최초 상태였으나, 다운로드 완료 후에는 존재함을 모의
    mock_exists.side_effect = [False, False, True]
    mock_getmtime.return_value = 0.0

    financial_dir = Path("data/financial_statements")
    service = FinancialSyncService(mock_drive_adapter, "file_123", financial_dir, mock_repository)

    success = await service.sync()

    assert success is True
    mock_drive_adapter.get_file_by_id.assert_called_once_with("file_123")
    mock_repository.load_all.assert_any_call(FinancialMetric.REVENUE)
    mock_repository.load_all.assert_any_call(FinancialMetric.OPERATING_PROFIT)
    mock_repository.load_all.assert_any_call(FinancialMetric.NET_INCOME)
