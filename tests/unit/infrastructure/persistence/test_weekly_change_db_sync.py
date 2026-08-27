import json
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from evenezer.infrastructure.persistence.weekly_change_db_sync import WeeklyChangeDbSync


def make_valid_db(path: Path, last_trading_day: str = "2026-07-03") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE events (id TEXT PRIMARY KEY, year INTEGER, week INTEGER, month INTEGER, "
        "week_of_month INTEGER, collected_at TEXT, day_of_week TEXT, last_trading_day TEXT, "
        "status TEXT, total_count INTEGER, fingerprint TEXT)"
    )
    conn.execute(
        "CREATE TABLE items (event_id TEXT, symbol_code TEXT, symbol_name TEXT, start_date TEXT, "
        "base_price REAL, end_date TEXT, close_price REAL, change REAL, change_rate REAL, "
        "volume INTEGER, amount INTEGER, in_kospi200 INTEGER DEFAULT 0, in_kosdaq150 INTEGER DEFAULT 0)"
    )
    conn.execute(
        "INSERT INTO events VALUES ('2026-W27', 2026, 27, 7, 1, '2026-07-03T00:00:00', 'Friday', ?, 'FINAL', 2870, '')",
        (last_trading_day,),
    )
    conn.commit()
    conn.close()


def make_corrupt_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not a sqlite file")


@pytest.fixture
def data_root(tmp_path):
    return tmp_path / "weekly_change_db"


@pytest.fixture
def mock_drive():
    drive = AsyncMock()
    return drive


def remote_meta(file_id="drive_id_1", mtime="2026-08-27T05:59:08.420Z", md5="abc123", size="364544"):
    return {"id": file_id, "modifiedTime": mtime, "md5Checksum": md5, "size": size}


@pytest.mark.asyncio
async def test_first_sync_downloads_and_saves_manifest(data_root, mock_drive):
    """매니페스트도 로컬 DB도 없을 때: 원격에서 전체 다운로드 후 저장."""
    sync = WeeklyChangeDbSync(drive_adapter=mock_drive, data_root=str(data_root))

    remote_db_path = data_root / "_remote_source" / "2026.db"
    make_valid_db(remote_db_path)
    content = remote_db_path.read_bytes()

    mock_drive.list_files_in_folder.return_value = [{"id": "drive_id_1", "name": "2026.db"}]
    mock_drive.get_file_metadata.return_value = remote_meta()
    mock_drive.get_file_by_id.return_value = content

    result = await sync.ensure_year_db(2026, is_monthly=False)

    assert result == sync._local_path(is_monthly=False, year=2026)
    assert result.exists()
    mock_drive.get_file_by_id.assert_called_once_with("drive_id_1")

    manifest = json.loads(sync.manifest_path.read_text(encoding="utf-8"))
    entry = manifest["weekly/2026.db"]
    assert entry["drive_file_id"] == "drive_id_1"
    assert entry["remote_md5_checksum"] == "abc123"
    assert entry["data_max_date"] == "2026-07-03"


@pytest.mark.asyncio
async def test_unchanged_remote_reuses_local_without_download(data_root, mock_drive):
    """매니페스트와 로컬 DB가 정상이고 원격 메타데이터가 일치하면 재다운로드하지 않는다."""
    sync = WeeklyChangeDbSync(drive_adapter=mock_drive, data_root=str(data_root))
    local_path = sync._local_path(is_monthly=False, year=2026)
    make_valid_db(local_path)

    meta = remote_meta()
    sync._save_manifest(
        {
            "weekly/2026.db": {
                "drive_file_id": meta["id"],
                "remote_modified_time": meta["modifiedTime"],
                "remote_md5_checksum": meta["md5Checksum"],
                "remote_size_bytes": meta["size"],
                "local_md5": "irrelevant",
                "local_size_bytes": local_path.stat().st_size,
                "data_max_date": "2026-07-03",
                "downloaded_at": "2026-08-27T00:00:00",
            }
        }
    )

    mock_drive.list_files_in_folder.return_value = [{"id": "drive_id_1", "name": "2026.db"}]
    mock_drive.get_file_metadata.return_value = meta

    result = await sync.ensure_year_db(2026, is_monthly=False)

    assert result == local_path
    mock_drive.get_file_by_id.assert_not_called()


@pytest.mark.asyncio
async def test_changed_remote_triggers_redownload(data_root, mock_drive):
    """원격 md5가 매니페스트와 다르면 다시 다운로드한다."""
    sync = WeeklyChangeDbSync(drive_adapter=mock_drive, data_root=str(data_root))
    local_path = sync._local_path(is_monthly=False, year=2026)
    make_valid_db(local_path, last_trading_day="2026-06-26")

    old_meta = remote_meta(md5="old_md5")
    sync._save_manifest(
        {
            "weekly/2026.db": {
                "drive_file_id": old_meta["id"],
                "remote_modified_time": old_meta["modifiedTime"],
                "remote_md5_checksum": old_meta["md5Checksum"],
                "remote_size_bytes": old_meta["size"],
                "local_md5": "old_local_md5",
                "local_size_bytes": local_path.stat().st_size,
                "data_max_date": "2026-06-26",
                "downloaded_at": "2026-08-20T00:00:00",
            }
        }
    )

    new_remote_db = data_root / "_remote_source" / "2026_new.db"
    make_valid_db(new_remote_db, last_trading_day="2026-07-03")
    new_content = new_remote_db.read_bytes()

    new_meta = remote_meta(md5="new_md5")
    mock_drive.list_files_in_folder.return_value = [{"id": "drive_id_1", "name": "2026.db"}]
    mock_drive.get_file_metadata.return_value = new_meta
    mock_drive.get_file_by_id.return_value = new_content

    result = await sync.ensure_year_db(2026, is_monthly=False)

    assert result == local_path
    mock_drive.get_file_by_id.assert_called_once_with("drive_id_1")
    manifest = json.loads(sync.manifest_path.read_text(encoding="utf-8"))
    assert manifest["weekly/2026.db"]["remote_md5_checksum"] == "new_md5"
    assert manifest["weekly/2026.db"]["data_max_date"] == "2026-07-03"


@pytest.mark.asyncio
async def test_missing_manifest_but_matching_local_regenerates_manifest_without_download(data_root, mock_drive):
    """매니페스트 없이 로컬 DB만 있고, 로컬 MD5가 원격과 일치하면 재다운로드 없이 매니페스트만 생성한다."""
    sync = WeeklyChangeDbSync(drive_adapter=mock_drive, data_root=str(data_root))
    local_path = sync._local_path(is_monthly=False, year=2026)
    make_valid_db(local_path)
    local_md5 = sync._md5(local_path)

    mock_drive.list_files_in_folder.return_value = [{"id": "drive_id_1", "name": "2026.db"}]
    mock_drive.get_file_metadata.return_value = remote_meta(md5=local_md5)

    result = await sync.ensure_year_db(2026, is_monthly=False)

    assert result == local_path
    mock_drive.get_file_by_id.assert_not_called()
    manifest = json.loads(sync.manifest_path.read_text(encoding="utf-8"))
    assert manifest["weekly/2026.db"]["remote_md5_checksum"] == local_md5


@pytest.mark.asyncio
async def test_missing_manifest_and_mismatched_local_redownloads(data_root, mock_drive):
    """매니페스트 없이 로컬 DB가 있지만 원격과 MD5가 다르면 재다운로드한다."""
    sync = WeeklyChangeDbSync(drive_adapter=mock_drive, data_root=str(data_root))
    local_path = sync._local_path(is_monthly=False, year=2026)
    make_valid_db(local_path, last_trading_day="2026-06-26")

    new_remote_db = data_root / "_remote_source" / "2026_new.db"
    make_valid_db(new_remote_db, last_trading_day="2026-07-03")
    new_content = new_remote_db.read_bytes()

    mock_drive.list_files_in_folder.return_value = [{"id": "drive_id_1", "name": "2026.db"}]
    mock_drive.get_file_metadata.return_value = remote_meta(md5="different_md5")
    mock_drive.get_file_by_id.return_value = new_content

    result = await sync.ensure_year_db(2026, is_monthly=False)

    assert result == local_path
    mock_drive.get_file_by_id.assert_called_once()
    manifest = json.loads(sync.manifest_path.read_text(encoding="utf-8"))
    assert manifest["weekly/2026.db"]["data_max_date"] == "2026-07-03"


@pytest.mark.asyncio
async def test_corrupt_local_with_valid_manifest_is_treated_as_cache_miss(data_root, mock_drive):
    """매니페스트가 최신이라고 해도 로컬 파일이 손상되었으면 재다운로드한다."""
    sync = WeeklyChangeDbSync(drive_adapter=mock_drive, data_root=str(data_root))
    local_path = sync._local_path(is_monthly=False, year=2026)
    make_corrupt_db(local_path)

    meta = remote_meta()
    sync._save_manifest(
        {
            "weekly/2026.db": {
                "drive_file_id": meta["id"],
                "remote_modified_time": meta["modifiedTime"],
                "remote_md5_checksum": meta["md5Checksum"],
                "remote_size_bytes": meta["size"],
                "local_md5": "whatever",
                "local_size_bytes": 123,
                "data_max_date": "2026-07-03",
                "downloaded_at": "2026-08-27T00:00:00",
            }
        }
    )

    remote_db = data_root / "_remote_source" / "2026.db"
    make_valid_db(remote_db)
    content = remote_db.read_bytes()
    mock_drive.list_files_in_folder.return_value = [{"id": "drive_id_1", "name": "2026.db"}]
    mock_drive.get_file_metadata.return_value = meta
    mock_drive.get_file_by_id.return_value = content

    result = await sync.ensure_year_db(2026, is_monthly=False)

    assert result == local_path
    mock_drive.get_file_by_id.assert_called_once()
    assert sync._validate(local_path) is True


@pytest.mark.asyncio
async def test_remote_metadata_fetch_failure_falls_back_to_valid_local_as_stale(data_root, mock_drive):
    """원격 확인이 실패하면 검증된 로컬 DB를 그대로 반환한다 (stale 허용, 크래시 없음)."""
    sync = WeeklyChangeDbSync(drive_adapter=mock_drive, data_root=str(data_root))
    local_path = sync._local_path(is_monthly=False, year=2026)
    make_valid_db(local_path)

    mock_drive.list_files_in_folder.return_value = [{"id": "drive_id_1", "name": "2026.db"}]
    mock_drive.get_file_metadata.return_value = None

    result = await sync.ensure_year_db(2026, is_monthly=False)

    assert result == local_path
    mock_drive.get_file_by_id.assert_not_called()


@pytest.mark.asyncio
async def test_remote_metadata_fetch_failure_no_local_returns_none(data_root, mock_drive):
    """원격 확인 실패 + 로컬 DB도 없으면 명확히 None을 반환한다 (빈 값으로 위장하지 않음)."""
    sync = WeeklyChangeDbSync(drive_adapter=mock_drive, data_root=str(data_root))

    mock_drive.list_files_in_folder.return_value = [{"id": "drive_id_1", "name": "2026.db"}]
    mock_drive.get_file_metadata.return_value = None

    result = await sync.ensure_year_db(2026, is_monthly=False)

    assert result is None


@pytest.mark.asyncio
async def test_remote_file_not_found_falls_back_to_local(data_root, mock_drive):
    """원격 목록에 해당 연도 파일이 없으면 유효한 로컬 DB를 그대로 사용한다."""
    sync = WeeklyChangeDbSync(drive_adapter=mock_drive, data_root=str(data_root))
    local_path = sync._local_path(is_monthly=False, year=2026)
    make_valid_db(local_path)

    mock_drive.list_files_in_folder.return_value = []

    result = await sync.ensure_year_db(2026, is_monthly=False)

    assert result == local_path


@pytest.mark.asyncio
async def test_downloaded_content_fails_validation_keeps_old_local(data_root, mock_drive):
    """다운로드한 내용이 손상됐으면 로컬을 덮어쓰지 않고 기존 유효 로컬을 유지한다."""
    sync = WeeklyChangeDbSync(drive_adapter=mock_drive, data_root=str(data_root))
    local_path = sync._local_path(is_monthly=False, year=2026)
    make_valid_db(local_path, last_trading_day="2026-06-26")

    meta = remote_meta(md5="new_md5")
    sync._save_manifest(
        {
            "weekly/2026.db": {
                "drive_file_id": "drive_id_1",
                "remote_modified_time": "old_time",
                "remote_md5_checksum": "old_md5",
                "remote_size_bytes": "1",
                "local_md5": "x",
                "local_size_bytes": local_path.stat().st_size,
                "data_max_date": "2026-06-26",
                "downloaded_at": "2026-08-20T00:00:00",
            }
        }
    )

    mock_drive.list_files_in_folder.return_value = [{"id": "drive_id_1", "name": "2026.db"}]
    mock_drive.get_file_metadata.return_value = meta
    mock_drive.get_file_by_id.return_value = b"corrupted bytes"

    result = await sync.ensure_year_db(2026, is_monthly=False)

    assert result == local_path
    assert sync._validate(local_path) is True
    manifest = json.loads(sync.manifest_path.read_text(encoding="utf-8"))
    assert manifest["weekly/2026.db"]["data_max_date"] == "2026-06-26"


@pytest.mark.asyncio
async def test_monthly_uses_separate_manifest_key_and_path(data_root, mock_drive):
    """weekly/monthly는 서로 다른 매니페스트 키와 로컬 경로를 사용한다."""
    sync = WeeklyChangeDbSync(drive_adapter=mock_drive, data_root=str(data_root))
    remote_db_path = data_root / "_remote_source" / "2026m.db"
    make_valid_db(remote_db_path, last_trading_day="2026-06-30")
    content = remote_db_path.read_bytes()

    mock_drive.list_files_in_folder.return_value = [{"id": "drive_id_m", "name": "2026.db"}]
    mock_drive.get_file_metadata.return_value = remote_meta(file_id="drive_id_m")
    mock_drive.get_file_by_id.return_value = content

    result = await sync.ensure_year_db(2026, is_monthly=True)

    assert result == sync._local_path(is_monthly=True, year=2026)
    assert result != sync._local_path(is_monthly=False, year=2026)
    manifest = json.loads(sync.manifest_path.read_text(encoding="utf-8"))
    assert "monthly/2026.db" in manifest
