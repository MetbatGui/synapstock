"""CeilingAnalysisService 유닛 테스트 (TDD: 구현보다 먼저 작성).

ceiling DB SSOT 구독으로 전환한 뒤의 공개 계약(get_ceiling_analysis/sync_data/
list_available_dates/list_available_years)을 검증한다. DB 동기화/쿼리는
fixture DB로 실제 SQLite를 써서 검증한다.
"""
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from evenezer.application.services.ceiling_analysis_service import CeilingAnalysisService


def make_ceiling_db(path: Path, cohort_stocks: list[tuple], price_history: list[tuple]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE cohort_stocks (cohort_date TEXT, stock_code TEXT, stock_name TEXT, "
        "new_high_status TEXT, initial_price INTEGER, PRIMARY KEY (cohort_date, stock_code))"
    )
    conn.execute(
        "CREATE TABLE price_history (cohort_date TEXT, stock_code TEXT, price_date TEXT, "
        "price INTEGER, PRIMARY KEY (cohort_date, stock_code, price_date))"
    )
    conn.executemany("INSERT INTO cohort_stocks VALUES (?,?,?,?,?)", cohort_stocks)
    conn.executemany("INSERT INTO price_history VALUES (?,?,?,?)", price_history)
    conn.commit()
    conn.close()


@pytest.fixture
def mock_repo():
    repo = MagicMock()
    repo.load_report.return_value = None
    repo.list_available_dates.return_value = []
    return repo


@pytest.fixture
def db_sync_stub(tmp_path):
    paths: dict[int, Path] = {}

    def register(year: int, cohort_stocks: list[tuple], price_history: list[tuple] | None = None):
        p = tmp_path / f"{year}.db"
        make_ceiling_db(p, cohort_stocks, price_history or [])
        paths[year] = p

    async def ensure_db(year, force=False):
        return paths.get(year)

    stub = MagicMock()
    stub.ensure_db = AsyncMock(side_effect=ensure_db)
    stub.register = register
    return stub


@pytest.fixture
def service(mock_repo, db_sync_stub):
    drive = MagicMock()
    return CeilingAnalysisService(drive, "ceiling", mock_repo, db_sync=db_sync_stub)


@pytest.mark.asyncio
async def test_sync_data_no_drive_adapter_returns_empty(mock_repo, db_sync_stub):
    service = CeilingAnalysisService(None, "ceiling", mock_repo, db_sync=db_sync_stub)
    assert await service.sync_data("2026-08-28") == []
    db_sync_stub.ensure_db.assert_not_called()


@pytest.mark.asyncio
async def test_sync_data_no_remote_db_returns_empty(service, db_sync_stub):
    result = await service.sync_data("2026-08-28")
    assert result == []


@pytest.mark.asyncio
async def test_sync_data_uses_year_from_date_str(service, db_sync_stub):
    db_sync_stub.register(2025, [])
    await service.sync_data("2025-12-30")
    db_sync_stub.ensure_db.assert_called_once_with(2025, force=False)


@pytest.mark.asyncio
async def test_sync_data_propagates_force_flag(service, db_sync_stub):
    db_sync_stub.register(2026, [])
    await service.sync_data("2026-08-28", force=True)
    db_sync_stub.ensure_db.assert_called_once_with(2026, force=True)


@pytest.mark.asyncio
async def test_sync_data_builds_one_report_per_cohort_and_saves(service, mock_repo, db_sync_stub):
    db_sync_stub.register(
        2026,
        cohort_stocks=[
            ("2026-08-28", "005930", "삼성전자", "신규", 70000),
            ("2026-08-27", "000660", "SK하이닉스", "", 100000),
        ],
        price_history=[
            ("2026-08-28", "005930", "2026-08-31", 75000),
        ],
    )

    reports = await service.sync_data("2026-08-28")

    assert len(reports) == 2
    end_dates = {r.end_date for r in reports}
    assert end_dates == {"2026-08-28", "2026-08-27"}
    mock_repo.save_report.assert_called_once()  # save_report(list) 한 번 호출


@pytest.mark.asyncio
async def test_sync_data_maps_item_fields_correctly(service, db_sync_stub):
    db_sync_stub.register(
        2026,
        cohort_stocks=[("2026-08-28", "005930", "삼성전자", "역사적신고가", 70000)],
        price_history=[("2026-08-28", "005930", "2026-08-31", 75000)],
    )

    reports = await service.sync_data("2026-08-28")

    report = reports[0]
    assert report.dates == ["08-28", "08-31"]
    item = report.items[0]
    assert item.name == "삼성전자"
    assert item.ticker == "005930"
    assert item.entry_tag == "역사적신고가"
    assert item.closing_prices == [70000, 75000]


@pytest.mark.asyncio
async def test_get_ceiling_analysis_returns_none_when_nothing_found(service, mock_repo, db_sync_stub):
    result = await service.get_ceiling_analysis("2026-08-28", force_sync=True)
    assert result is None


@pytest.mark.asyncio
async def test_get_ceiling_analysis_exact_date_match(service, mock_repo, db_sync_stub):
    db_sync_stub.register(
        2026,
        cohort_stocks=[("2026-08-28", "005930", "삼성전자", "", 70000)],
        price_history=[],
    )

    report = await service.get_ceiling_analysis("2026-08-28", force_sync=True)

    assert report is not None
    assert report.end_date == "2026-08-28"
    assert report.items[0].name == "삼성전자"
