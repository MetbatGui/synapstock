import sqlite3
from pathlib import Path

import pytest

from evenezer.infrastructure.persistence.weekly_change_db_query import (
    build_report,
    fetch_event_by_date,
    fetch_events,
    fetch_latest_event,
)


@pytest.fixture
def db_path(tmp_path) -> Path:
    path = tmp_path / "2026.db"
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
    conn.executemany(
        "INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("2026-W26", 2026, 26, 6, 4, "2026-07-03T14:45:44", "Friday", "2026-06-26", "FINAL", 2875, "f1"),
            ("2026-W27", 2026, 27, 7, 1, "2026-07-03T15:45:12", "Friday", "2026-07-03", "FINAL", 2870, "f2"),
            ("2026-W28", 2026, 28, 7, 2, "2026-07-10T15:45:00", "Friday", "2026-07-10", "RUNNING", 0, ""),
        ],
    )
    conn.executemany(
        "INSERT INTO items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            (
                "2026-W27",
                "005930",
                "삼성전자",
                "2026-06-29",
                68000.0,
                "2026-07-03",
                70000.0,
                2000.0,
                2.94,
                1000,
                70000000,
                1,
                0,
            ),
            (
                "2026-W27",
                "000660",
                "SK하이닉스",
                "2026-06-29",
                175000.0,
                "2026-07-03",
                180000.0,
                5000.0,
                2.86,
                500,
                90000000,
                1,
                1,
            ),
            (
                "2026-W27",
                "123456",
                "코스닥종목",
                "2026-06-29",
                1000.0,
                "2026-07-03",
                1300.0,
                300.0,
                30.0,
                200,
                260000,
                0,
                1,
            ),
            (
                "2026-W26",
                "005930",
                "삼성전자",
                "2026-06-22",
                65000.0,
                "2026-06-26",
                68000.0,
                3000.0,
                4.6,
                900,
                61000000,
                0,
                0,
            ),
        ],
    )
    conn.commit()
    conn.close()
    return path


def test_fetch_event_by_date_found(db_path):
    event = fetch_event_by_date(db_path, "2026-07-03")
    assert event is not None
    assert event["id"] == "2026-W27"
    assert event["year"] == 2026
    assert event["week"] == 27


def test_fetch_event_by_date_not_found(db_path):
    assert fetch_event_by_date(db_path, "2099-01-01") is None


def test_fetch_latest_event_skips_non_final(db_path):
    """RUNNING 상태는 제외하고, 완료된 이벤트 중 가장 최신을 반환한다."""
    event = fetch_latest_event(db_path)
    assert event is not None
    assert event["id"] == "2026-W27"


def test_fetch_events_ordered_desc(db_path):
    events = fetch_events(db_path)
    dates = [e["last_trading_day"] for e in events]
    assert dates == sorted(dates, reverse=True)
    assert len(events) == 3


@pytest.fixture
def event_0703(db_path):
    event = fetch_event_by_date(db_path, "2026-07-03")
    assert event is not None
    return event


def test_build_report_event_fields(db_path, event_0703):
    report = build_report(db_path, event_0703, is_monthly=False)

    assert report.date == "2026-07-03"
    assert report.year == 2026
    assert report.month == 7
    assert report.week_num == 27
    assert report.week_of_month == 1
    assert report.is_monthly is False


def test_build_report_all_items(db_path, event_0703):
    report = build_report(db_path, event_0703, is_monthly=False)

    assert len(report.items) == 3
    assert {i.name for i in report.items} == {"삼성전자", "SK하이닉스", "코스닥종목"}

    samsung = next(i for i in report.items if i.name == "삼성전자")
    assert samsung.ticker == "005930"
    assert samsung.close_price == 70000
    assert samsung.base_price == 68000
    assert samsung.change_rate == 2.94


def test_build_report_kospi200_items(db_path, event_0703):
    report = build_report(db_path, event_0703, is_monthly=False)

    assert len(report.kospi_200_items) == 2
    assert {i.name for i in report.kospi_200_items} == {"삼성전자", "SK하이닉스"}


def test_build_report_kosdaq150_items(db_path, event_0703):
    report = build_report(db_path, event_0703, is_monthly=False)

    assert len(report.kosdaq_150_items) == 2
    assert {i.name for i in report.kosdaq_150_items} == {"SK하이닉스", "코스닥종목"}


def test_build_report_date_range_from_items(db_path):
    event = fetch_event_by_date(db_path, "2026-07-03")
    assert event is not None
    report = build_report(db_path, event, is_monthly=False)
    assert report.date_range == "0629~0703"


def test_build_report_empty_items_has_none_date_range(db_path):
    """events.id가 items에 전혀 없는 경우(방어적 케이스) date_range는 None."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("2026-W29", 2026, 29, 7, 3, "2026-07-17T00:00:00", "Friday", "2026-07-17", "FINAL", 2000, ""),
    )
    conn.commit()
    conn.close()

    event = fetch_event_by_date(db_path, "2026-07-17")
    assert event is not None
    report = build_report(db_path, event, is_monthly=False)
    assert report.items == []
    assert report.date_range is None
