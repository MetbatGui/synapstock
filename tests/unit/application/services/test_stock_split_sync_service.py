import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch

from evenezer.application.services.stock_split_sync_service import StockSplitSyncService
from evenezer.domain.statistics.models import StockSplitManifest


@pytest.fixture
def mock_repository():
    repo = MagicMock()
    repo.load_manifest.return_value = None
    repo.get_file_mtime.return_value = None
    return repo


@pytest.fixture
def mock_drive_adapter():
    adapter = MagicMock()
    
    # list_files_in_folder 비동기 메소드 모의
    adapter.list_files_in_folder = AsyncMock(return_value=[
        {"id": "manifest_id", "name": "stock_splits_manifest.json", "mimeType": "application/json"},
        {"id": "excel_2024_id", "name": "주식분할_2024년.xlsx", "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
        {"id": "excel_2025_id", "name": "주식분할_2025년.xlsx", "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
    ])
    
    # get_file 비동기 메소드 모의
    adapter.get_file = AsyncMock()
    return adapter


@pytest.mark.asyncio
async def test_sync_successful(mock_repository, mock_drive_adapter):
    """최초 동기화 상황에서 매니페스트 및 엑셀 파일들을 모두 성공적으로 동기화하는지 검증."""
    service = StockSplitSyncService(
        repository=mock_repository,
        drive_adapter=mock_drive_adapter,
        stock_split_folder_id="folder_123"
    )

    # 1. 매니페스트 모의 데이터 준비
    manifest_dict = {
        "manifest_version": "1.0.0",
        "last_updated": "2026-05-27T15:00:00",
        "total_records": 10,
        "supported_years": ["2024", "2025"],
        "years_index": {"2024": [], "2025": []}
    }
    manifest_bytes = json.dumps(manifest_dict).encode("utf-8")
    
    # get_file 반환값 설정
    async def side_effect(name, root_id):
        if "manifest" in name:
            return manifest_bytes
        return b"fake excel bytes"
    mock_drive_adapter.get_file.side_effect = side_effect

    # 2. 동기화 실행
    success = await service.sync()
    
    # 검증: 성공 여부 및 저장 메서드 호출 검증
    assert success is True
    
    # 엑셀 파일 저장 검증
    mock_repository.save_excel_file.assert_any_call("액면분할(2024년).xlsx", b"fake excel bytes")
    mock_repository.save_excel_file.assert_any_call("액면분할(2025년).xlsx", b"fake excel bytes")
    
    # 매니페스트 저장 검증
    mock_repository.save_manifest.assert_called_once()
    saved_manifest = mock_repository.save_manifest.call_args[0][0]
    assert isinstance(saved_manifest, StockSplitManifest)
    assert saved_manifest.last_updated == "2026-05-27T15:00:00"


@pytest.mark.asyncio
async def test_sync_skipped_when_up_to_date(mock_repository, mock_drive_adapter):
    """로컬 데이터가 이미 최신이고 파일들이 존재하면 다운로드를 건너뛰는지 확인."""
    service = StockSplitSyncService(
        repository=mock_repository,
        drive_adapter=mock_drive_adapter,
        stock_split_folder_id="folder_123"
    )

    # 로컬 매니페스트 준비
    local_manifest = StockSplitManifest(
        manifest_version="1.0.0",
        last_updated="2026-05-27T15:00:00",
        total_records=10,
        supported_years=["2024", "2025"],
        years_index={"2024": [], "2025": []}
    )
    mock_repository.load_manifest.return_value = local_manifest
    
    # 로컬 파일들이 모두 존재(mtime > 0)
    mock_repository.get_file_mtime.return_value = 1715000000.0

    # 원격 매니페스트 준비 (동일 시각)
    manifest_bytes = json.dumps(local_manifest.model_dump()).encode("utf-8")
    mock_drive_adapter.get_file.return_value = manifest_bytes

    # 동기화 실행
    success = await service.sync()
    
    assert success is True
    # 엑셀 다운로드 및 저장이 호출되지 않아야 함
    mock_repository.save_excel_file.assert_not_called()
    mock_repository.save_manifest.assert_not_called()


@pytest.mark.asyncio
async def test_sync_force_runs_when_local_file_missing(mock_repository, mock_drive_adapter):
    """매니페스트 업데이트 시각은 동일하지만, 로컬 엑셀 파일이 하나라도 누락되면 동기화가 진행되는지 확인."""
    service = StockSplitSyncService(
        repository=mock_repository,
        drive_adapter=mock_drive_adapter,
        stock_split_folder_id="folder_123"
    )

    # 로컬 매니페스트 준비
    local_manifest = StockSplitManifest(
        manifest_version="1.0.0",
        last_updated="2026-05-27T15:00:00",
        total_records=10,
        supported_years=["2024", "2025"],
        years_index={"2024": [], "2025": []}
    )
    mock_repository.load_manifest.return_value = local_manifest
    
    # 2024년은 존재하고 2025년 파일은 누락된 상태 모의
    def mock_mtime(filename):
        if "2024" in filename:
            return 1715000000.0
        return None  # 누락
    mock_repository.get_file_mtime.side_effect = mock_mtime

    # 원격 매니페스트 준비
    manifest_bytes = json.dumps(local_manifest.model_dump()).encode("utf-8")
    
    async def side_effect(name, root_id):
        if "manifest" in name:
            return manifest_bytes
        return b"fake excel bytes"
    mock_drive_adapter.get_file.side_effect = side_effect

    # 동기화 실행
    success = await service.sync()
    
    assert success is True
    # 엑셀 파일 저장이 호출되어 복구되어야 함
    mock_repository.save_excel_file.assert_any_call("액면분할(2025년).xlsx", b"fake excel bytes")
