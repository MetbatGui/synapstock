import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from evenezer.infrastructure.persistence.yearly_db_sync import YearlyDbSync


def make_valid_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE netbuy (date_str TEXT)")
    conn.execute("CREATE TABLE price_info (date_str TEXT)")
    conn.commit()
    conn.close()


def make_corrupt_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not a sqlite file")


@pytest.fixture
def data_root(tmp_path):
    return tmp_path / "netbuy_db"


@pytest.fixture
def mock_drive():
    return AsyncMock()


def remote_meta(file_id="drive_id_1", mtime="2026-08-27T05:59:08.420Z", md5="abc123", size="364544"):
    return {"id": file_id, "modifiedTime": mtime, "md5Checksum": md5, "size": size}


def make_sync(drive, data_root) -> YearlyDbSync:
    return YearlyDbSync(
        drive_adapter=drive,
        data_root=str(data_root),
        folder_name="sd",
        filename_for_year=lambda year: f"market_data_{year}.db",
        required_tables={"netbuy", "price_info"},
    )


@pytest.mark.asyncio
async def test_no_drive_adapter_returns_none(data_root):
    sync = YearlyDbSync(
        drive_adapter=None, data_root=str(data_root), folder_name="sd",
        filename_for_year=lambda y: f"market_data_{y}.db", required_tables={"netbuy"},
    )
    assert await sync.ensure_db(2026) is None


@pytest.mark.asyncio
async def test_first_sync_downloads_and_saves_manifest(data_root, mock_drive):
    sync = make_sync(mock_drive, data_root)
    remote_db_path = data_root / "_remote_source" / "market_data_2026.db"
    make_valid_db(remote_db_path)
    content = remote_db_path.read_bytes()

    mock_drive.list_files_in_folder.return_value = [{"id": "drive_id_1", "name": "market_data_2026.db"}]
    mock_drive.get_file_metadata.return_value = remote_meta()
    mock_drive.get_file_by_id.return_value = content

    result = await sync.ensure_db(2026)

    assert result == sync._local_path(2026)
    assert result.read_bytes() == content
    manifest = json.loads(sync.manifest_path.read_text(encoding="utf-8"))
    assert "market_data_2026.db" in manifest
    assert manifest["market_data_2026.db"]["last_checked_at"]


@pytest.mark.asyncio
async def test_remote_file_not_found_falls_back_to_valid_local(data_root, mock_drive):
    sync = make_sync(mock_drive, data_root)
    local_path = sync._local_path(2026)
    make_valid_db(local_path)
    mock_drive.list_files_in_folder.return_value = []

    result = await sync.ensure_db(2026)

    assert result == local_path
    mock_drive.get_file_metadata.assert_not_called()


@pytest.mark.asyncio
async def test_remote_file_not_found_and_no_local_returns_none(data_root, mock_drive):
    sync = make_sync(mock_drive, data_root)
    mock_drive.list_files_in_folder.return_value = []

    assert await sync.ensure_db(2026) is None


@pytest.mark.asyncio
async def test_repeated_calls_for_permanently_missing_year_are_ttl_cached(data_root, mock_drive):
    """존재하지 않는 연도(예: 아직 발행 전 미래 연도)를 매 요청마다 확인하면 Drive를
    영원히 두들기게 된다 - "없음" 결과도 TTL로 캐시해야 한다."""
    sync = make_sync(mock_drive, data_root)
    mock_drive.list_files_in_folder.return_value = []

    result1 = await sync.ensure_db(2099)
    result2 = await sync.ensure_db(2099)

    assert result1 is None
    assert result2 is None
    assert mock_drive.list_files_in_folder.call_count == 1  # 두 번째 호출은 TTL에 막혀 생략


@pytest.mark.asyncio
async def test_force_bypasses_ttl_even_for_missing_year(data_root, mock_drive):
    sync = make_sync(mock_drive, data_root)
    mock_drive.list_files_in_folder.return_value = []

    await sync.ensure_db(2099)
    await sync.ensure_db(2099, force=True)

    assert mock_drive.list_files_in_folder.call_count == 2


@pytest.mark.asyncio
async def test_corrupt_local_triggers_redownload_even_without_manifest(data_root, mock_drive):
    sync = make_sync(mock_drive, data_root)
    local_path = sync._local_path(2026)
    make_corrupt_db(local_path)

    remote_db_path = data_root / "_remote_source" / "market_data_2026.db"
    make_valid_db(remote_db_path)
    content = remote_db_path.read_bytes()

    mock_drive.list_files_in_folder.return_value = [{"id": "drive_id_1", "name": "market_data_2026.db"}]
    mock_drive.get_file_metadata.return_value = remote_meta()
    mock_drive.get_file_by_id.return_value = content

    result = await sync.ensure_db(2026)

    assert result == local_path
    assert local_path.read_bytes() == content


@pytest.mark.asyncio
async def test_download_failure_keeps_valid_local_as_stale(data_root, mock_drive):
    sync = make_sync(mock_drive, data_root)
    local_path = sync._local_path(2026)
    make_valid_db(local_path)

    mock_drive.list_files_in_folder.return_value = [{"id": "drive_id_1", "name": "market_data_2026.db"}]
    mock_drive.get_file_metadata.return_value = remote_meta(md5="different_md5")
    mock_drive.get_file_by_id.return_value = None  # 다운로드 실패

    result = await sync.ensure_db(2026)

    assert result == local_path  # stale 로컬 유지


# ---------------------------------------------------------------------------
# TTL / force
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_within_ttl_skips_remote_calls(data_root, mock_drive):
    sync = make_sync(mock_drive, data_root)
    local_path = sync._local_path(2026)
    make_valid_db(local_path)
    sync._save_manifest(
        {
            "market_data_2026.db": {
                "drive_file_id": "d1", "remote_modified_time": "t", "remote_md5_checksum": "m",
                "remote_size_bytes": "1", "local_md5": "x", "local_size_bytes": local_path.stat().st_size,
                "downloaded_at": "2026-01-01T00:00:00+00:00",
                "last_checked_at": datetime.now(UTC).isoformat(),
            }
        }
    )

    result = await sync.ensure_db(2026)

    assert result == local_path
    mock_drive.list_files_in_folder.assert_not_called()


@pytest.mark.asyncio
async def test_force_bypasses_ttl(data_root, mock_drive):
    sync = make_sync(mock_drive, data_root)
    local_path = sync._local_path(2026)
    make_valid_db(local_path)
    sync._save_manifest(
        {
            "market_data_2026.db": {
                "drive_file_id": "d1", "remote_modified_time": "t", "remote_md5_checksum": "m",
                "remote_size_bytes": "1", "local_md5": "x", "local_size_bytes": local_path.stat().st_size,
                "downloaded_at": datetime.now(UTC).isoformat(),
                "last_checked_at": datetime.now(UTC).isoformat(),
            }
        }
    )
    mock_drive.list_files_in_folder.return_value = [{"id": "d1", "name": "market_data_2026.db"}]
    mock_drive.get_file_metadata.return_value = remote_meta(file_id="d1", mtime="t", md5="m")

    result = await sync.ensure_db(2026, force=True)

    assert result == local_path
    mock_drive.get_file_metadata.assert_called_once()


# ---------------------------------------------------------------------------
# 중첩 서브폴더 지원 (예: ceiling의 "db/{year}.db" - "ceiling" 루트 안에 "db"
# 서브폴더가 하나 더 있고 그 안에 연도별 파일이 있음)
# ---------------------------------------------------------------------------

def make_sync_with_subfolder(drive, data_root) -> YearlyDbSync:
    return YearlyDbSync(
        drive_adapter=drive,
        data_root=str(data_root),
        folder_name="ceiling",
        subfolder="db",
        filename_for_year=lambda year: f"{year}.db",
        required_tables={"cohort_stocks", "price_history"},
    )


@pytest.mark.asyncio
async def test_subfolder_resolves_nested_folder_before_listing_files(data_root, mock_drive):
    sync = make_sync_with_subfolder(mock_drive, data_root)
    remote_db_path = data_root / "_remote_source" / "2026.db"
    remote_db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(remote_db_path)
    conn.execute("CREATE TABLE cohort_stocks (x TEXT)")
    conn.execute("CREATE TABLE price_history (x TEXT)")
    conn.commit()
    conn.close()
    content = remote_db_path.read_bytes()

    # 1단계: "ceiling" 루트에서 "db" 서브폴더를 찾는다.
    # 2단계: 그 서브폴더 id로 다시 목록 조회해 "2026.db"를 찾는다.
    mock_drive.list_files_in_folder.side_effect = [
        [{"id": "db_folder_id", "name": "db"}],
        [{"id": "drive_id_1", "name": "2026.db"}],
    ]
    mock_drive.get_file_metadata.return_value = remote_meta()
    mock_drive.get_file_by_id.return_value = content

    result = await sync.ensure_db(2026)

    assert result == sync._local_path(2026)
    assert result.read_bytes() == content
    first_call = mock_drive.list_files_in_folder.call_args_list[0]
    assert first_call.kwargs.get("folder") == "ceiling"
    second_call = mock_drive.list_files_in_folder.call_args_list[1]
    assert second_call.kwargs.get("root_id") == "db_folder_id"


@pytest.mark.asyncio
async def test_subfolder_not_found_falls_back_to_valid_local(data_root, mock_drive):
    sync = make_sync_with_subfolder(mock_drive, data_root)
    local_path = sync._local_path(2026)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(local_path)
    conn.execute("CREATE TABLE cohort_stocks (x TEXT)")
    conn.execute("CREATE TABLE price_history (x TEXT)")
    conn.commit()
    conn.close()

    mock_drive.list_files_in_folder.return_value = []  # "db" 서브폴더 자체가 없음

    result = await sync.ensure_db(2026)

    assert result == local_path
    mock_drive.get_file_metadata.assert_not_called()


@pytest.mark.asyncio
async def test_ttl_expired_rechecks_and_touches_last_checked(data_root, mock_drive):
    sync = make_sync(mock_drive, data_root)
    local_path = sync._local_path(2026)
    make_valid_db(local_path)
    stale = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
    sync._save_manifest(
        {
            "market_data_2026.db": {
                "drive_file_id": "d1", "remote_modified_time": "t", "remote_md5_checksum": "m",
                "remote_size_bytes": "1", "local_md5": "x", "local_size_bytes": local_path.stat().st_size,
                "downloaded_at": stale, "last_checked_at": stale,
            }
        }
    )
    mock_drive.list_files_in_folder.return_value = [{"id": "d1", "name": "market_data_2026.db"}]
    mock_drive.get_file_metadata.return_value = remote_meta(file_id="d1", mtime="t", md5="m")

    result = await sync.ensure_db(2026)

    assert result == local_path
    mock_drive.get_file_by_id.assert_not_called()  # 변경 없음 - 재다운로드 안 함
    manifest = json.loads(sync.manifest_path.read_text(encoding="utf-8"))
    assert manifest["market_data_2026.db"]["last_checked_at"] != stale
