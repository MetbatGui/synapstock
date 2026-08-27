import sqlite3
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from evenezer.application.services.weekly_change_service import WeeklyChangeService
from evenezer.domain.statistics.models import WeeklyChangeReport

CURRENT_YEAR = datetime.now().year


def make_db(path: Path, events: list[tuple], items: list[tuple]) -> None:
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
    conn.executemany("INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?)", events)
    if items:
        conn.executemany("INSERT INTO items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", items)
    conn.commit()
    conn.close()


def weekly_event(event_id, week, month, week_of_month, last_trading_day, status="FINAL"):
    return (
        event_id,
        CURRENT_YEAR,
        week,
        month,
        week_of_month,
        "2026-01-01T00:00:00",
        "Friday",
        last_trading_day,
        status,
        2870,
        "",
    )


def monthly_event(event_id, month, last_trading_day, status="FINAL"):
    return (event_id, CURRENT_YEAR, 0, month, 0, "2026-01-01T00:00:00", "Friday", last_trading_day, status, 2870, "")


def item(event_id, start_date, end_date, in_kospi200=0, in_kosdaq150=0):
    return (
        event_id,
        "005930",
        "삼성전자",
        start_date,
        68000.0,
        end_date,
        70000.0,
        2000.0,
        2.94,
        1000,
        70000000,
        in_kospi200,
        in_kosdaq150,
    )


@pytest.fixture
def mock_repo():
    repo = MagicMock()
    repo.load_report.return_value = None
    repo.list_available_dates.return_value = []
    return repo


@pytest.fixture
def db_sync_stub(tmp_path):
    """(year, is_monthly)별로 등록된 fixture DB 경로만 반환하는 db_sync 스텁."""
    paths: dict[tuple[int, bool], Path] = {}

    def register(year: int, is_monthly: bool, events: list[tuple], items: list[tuple] | None = None):
        p = tmp_path / f"{'m' if is_monthly else 'w'}_{year}.db"
        make_db(p, events, items or [])
        paths[(year, is_monthly)] = p

    async def ensure_year_db(year, is_monthly):
        return paths.get((year, is_monthly))

    stub = MagicMock()
    stub.ensure_year_db = AsyncMock(side_effect=ensure_year_db)
    stub.register = register
    return stub


@pytest.fixture
def service(mock_repo, db_sync_stub):
    drive = MagicMock()
    return WeeklyChangeService(drive_adapter=drive, folder_id="folder_123", repository=mock_repo, db_sync=db_sync_stub)


def test_service_init(mock_repo, db_sync_stub):
    drive = MagicMock()
    service = WeeklyChangeService(
        drive_adapter=drive, folder_id="folder_123", repository=mock_repo, db_sync=db_sync_stub
    )
    assert service.drive_adapter == drive
    assert service.folder_id == "folder_123"
    assert service.repository == mock_repo
    assert service.get_service_name() == "WeeklyChangeService"


@pytest.mark.asyncio
async def test_get_weekly_change_from_local_cache_skips_sync(service, mock_repo, db_sync_stub):
    """force_sync=False이고 로컬 캐시가 있으면 DB 동기화를 시도하지 않는다."""
    cached = WeeklyChangeReport(date="2026-07-03", year=2026, items=[])
    mock_repo.load_report.return_value = cached

    result = await service.get_weekly_change(date="2026-07-03", force_sync=False)

    assert result == cached
    db_sync_stub.ensure_year_db.assert_not_called()


@pytest.mark.asyncio
async def test_get_weekly_change_cache_miss_calls_sync_data(service, mock_repo, monkeypatch):
    mock_repo.load_report.return_value = None
    called = {}

    async def fake_sync(date_str):
        called["date"] = date_str
        return "sentinel"

    monkeypatch.setattr(service, "sync_data", fake_sync)
    result = await service.get_weekly_change(date="2026-07-03", force_sync=False)

    assert result == "sentinel"
    assert called["date"] == "2026-07-03"


@pytest.mark.asyncio
async def test_get_weekly_change_force_sync_ignores_cache(service, mock_repo, db_sync_stub):
    """force_sync=True면 로컬 캐시가 있어도 동기화를 수행한다."""
    mock_repo.load_report.return_value = WeeklyChangeReport(date="2026-07-03", year=2026, items=[])
    db_sync_stub.register(
        CURRENT_YEAR,
        False,
        [weekly_event("2026-W27", 27, 7, 1, "2026-07-03")],
        [item("2026-W27", "2026-06-29", "2026-07-03")],
    )

    result = await service.get_weekly_change(date="2026-07-03", force_sync=True)

    assert result is not None
    assert result.items[0].name == "삼성전자"
    mock_repo.save_report.assert_called_once()


@pytest.mark.asyncio
async def test_sync_data_no_drive_adapter_returns_none(mock_repo, db_sync_stub):
    service = WeeklyChangeService(drive_adapter=None, folder_id="f", repository=mock_repo, db_sync=db_sync_stub)
    assert await service.sync_data("2026-07-03") is None
    db_sync_stub.ensure_year_db.assert_not_called()


@pytest.mark.asyncio
async def test_sync_data_finds_weekly_event_and_saves(service, mock_repo, db_sync_stub):
    db_sync_stub.register(
        CURRENT_YEAR,
        False,
        [weekly_event("2026-W27", 27, 7, 1, "2026-07-03")],
        [item("2026-W27", "2026-06-29", "2026-07-03", in_kospi200=1)],
    )

    report = await service.sync_data("2026-07-03")

    assert report.date == "2026-07-03"
    assert report.is_monthly is False
    assert len(report.items) == 1
    assert len(report.kospi_200_items) == 1
    mock_repo.save_report.assert_called_once_with(report)


@pytest.mark.asyncio
async def test_sync_data_falls_back_to_monthly_when_not_in_weekly(service, mock_repo, db_sync_stub):
    db_sync_stub.register(CURRENT_YEAR, False, [weekly_event("2026-W27", 27, 7, 1, "2026-07-03")], [])
    db_sync_stub.register(
        CURRENT_YEAR,
        True,
        [monthly_event("2026-M06", 6, "2026-06-30")],
        [item("2026-M06", "2026-06-01", "2026-06-30")],
    )

    report = await service.sync_data("2026-06-30")

    assert report is not None
    assert report.is_monthly is True
    assert report.date == "2026-06-30"


@pytest.mark.asyncio
async def test_sync_data_no_match_returns_none(service, mock_repo, db_sync_stub):
    db_sync_stub.register(CURRENT_YEAR, False, [weekly_event("2026-W27", 27, 7, 1, "2026-07-03")], [])
    db_sync_stub.register(CURRENT_YEAR, True, [monthly_event("2026-M06", 6, "2026-06-30")], [])

    report = await service.sync_data("2026-12-31")

    assert report is None
    mock_repo.save_report.assert_not_called()


@pytest.mark.asyncio
async def test_sync_data_latest_picks_most_recent_across_types_and_years(service, mock_repo, db_sync_stub):
    """date_str 없이 호출 시 올해/작년, weekly/monthly 전체 중 가장 최신 완료 이벤트를 고른다."""
    db_sync_stub.register(CURRENT_YEAR, False, [weekly_event("2026-W27", 27, 7, 1, "2026-07-03")], [])
    db_sync_stub.register(CURRENT_YEAR, True, [monthly_event("2026-M07", 7, "2026-07-31")], [])
    db_sync_stub.register(CURRENT_YEAR - 1, False, [weekly_event("2025-W52", 52, 12, 5, "2025-12-26")], [])

    report = await service.sync_data(None)

    assert report is not None
    assert report.date == "2026-07-31"
    assert report.is_monthly is True


@pytest.mark.asyncio
async def test_sync_data_latest_ignores_running_events(service, mock_repo, db_sync_stub):
    db_sync_stub.register(
        CURRENT_YEAR,
        False,
        [
            weekly_event("2026-W27", 27, 7, 1, "2026-07-03", status="FINAL"),
            weekly_event("2026-W28", 28, 7, 2, "2026-07-10", status="RUNNING"),
        ],
        [],
    )

    report = await service.sync_data(None)

    assert report.date == "2026-07-03"


@pytest.mark.asyncio
async def test_sync_data_latest_returns_none_when_no_db_available(mock_repo, db_sync_stub):
    drive = MagicMock()
    service = WeeklyChangeService(drive_adapter=drive, folder_id="f", repository=mock_repo, db_sync=db_sync_stub)
    assert await service.sync_data(None) is None


@pytest.mark.asyncio
async def test_list_available_dates_merges_local_and_cloud_without_duplicates(service, mock_repo, db_sync_stub):
    local_report = WeeklyChangeReport(date="2026-06-26", year=2026, month=6, items=[])
    mock_repo.list_available_dates.return_value = ["2026-06-26"]
    mock_repo.load_report.return_value = local_report

    db_sync_stub.register(
        CURRENT_YEAR,
        False,
        [
            weekly_event("2026-W26", 26, 6, 4, "2026-06-26"),  # 로컬에 이미 있음 -> 중복 제외
            weekly_event("2026-W27", 27, 7, 1, "2026-07-03"),  # 새 항목
            weekly_event("2026-W28", 28, 7, 2, "2026-07-10", status="RUNNING"),  # 미완료 -> 제외
        ],
        [],
    )
    db_sync_stub.register(CURRENT_YEAR, True, [], [])

    results = await service.list_available_dates()

    dates = [r["date"] for r in results]
    assert dates == ["2026-07-03", "2026-06-26"]
    assert results[0]["source"] == "cloud"
    assert results[1]["source"] == "local"


@pytest.mark.asyncio
async def test_list_available_dates_keeps_monthly_when_date_collides_with_weekly(service, mock_repo, db_sync_stub):
    """월간 이벤트의 last_trading_day가 주간 이벤트와 우연히 같아도 둘 다 살아남아야 한다.

    실데이터에서 월말 마지막 거래일이 그 주의 금요일 마감일과 같은 날짜인 경우가 흔하다
    (예: 2026-07-31이 7월의 마지막 거래일이면서 동시에 어느 주의 금요일 마감일).
    """
    db_sync_stub.register(CURRENT_YEAR, False, [weekly_event("2026-W31", 31, 7, 5, "2026-07-31")], [])
    db_sync_stub.register(CURRENT_YEAR, True, [monthly_event("2026-M07", 7, "2026-07-31")], [])

    results = await service.list_available_dates()

    weekly_entry = next(r for r in results if not r["is_monthly"])
    monthly_entry = next(r for r in results if r["is_monthly"])
    assert weekly_entry["date"] == "2026-07-31"
    assert monthly_entry["date"] == "2026-07-31"
