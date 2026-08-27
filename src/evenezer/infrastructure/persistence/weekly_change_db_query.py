"""weekly_change SQLite DB(events/items)에서 WeeklyChangeReport를 조립하는 읽기 전용 조회 계층."""

import sqlite3
from pathlib import Path

from evenezer.domain.statistics.models import WeeklyChangeItem, WeeklyChangeReport

_EVENTS_WITH_RANGE_SQL = """
    SELECT e.*, MIN(i.start_date) AS range_start, MAX(i.end_date) AS range_end
    FROM events e
    LEFT JOIN items i ON i.event_id = e.id
    GROUP BY e.id
    ORDER BY e.last_trading_day DESC
"""

_FINAL_STATUSES = ("COMPLETED", "FINAL")


def _connect_ro(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_events(db_path: Path) -> list[sqlite3.Row]:
    """전체 이벤트를 최신순으로, 각 이벤트의 실제 데이터 기간(items 기반)과 함께 반환한다."""
    conn = _connect_ro(db_path)
    try:
        return conn.execute(_EVENTS_WITH_RANGE_SQL).fetchall()
    finally:
        conn.close()


def fetch_event_by_date(db_path: Path, date_str: str) -> sqlite3.Row | None:
    return next((e for e in fetch_events(db_path) if e["last_trading_day"] == date_str), None)


def fetch_latest_event(db_path: Path) -> sqlite3.Row | None:
    return next((e for e in fetch_events(db_path) if e["status"] in _FINAL_STATUSES), None)


def _event_date_range(event_row: sqlite3.Row) -> str | None:
    start, end = event_row["range_start"], event_row["range_end"]
    if not start or not end:
        return None
    return f"{start[5:7]}{start[8:10]}~{end[5:7]}{end[8:10]}"


def _row_to_item(row: sqlite3.Row) -> WeeklyChangeItem:
    return WeeklyChangeItem(
        name=row["symbol_name"],
        ticker=row["symbol_code"],
        close_price=int(round(row["close_price"] or 0)),
        base_price=int(round(row["base_price"] or 0)),
        change_rate=row["change_rate"] or 0.0,
    )


def build_report(db_path: Path, event_row: sqlite3.Row, is_monthly: bool) -> WeeklyChangeReport:
    """단일 이벤트 행과 그에 속한 items를 조합해 WeeklyChangeReport를 조립한다."""
    conn = _connect_ro(db_path)
    try:
        item_rows = conn.execute("SELECT * FROM items WHERE event_id = ?", (event_row["id"],)).fetchall()
    finally:
        conn.close()

    all_items, kospi_items, kosdaq_items = [], [], []
    for row in item_rows:
        item = _row_to_item(row)
        all_items.append(item)
        if row["in_kospi200"]:
            kospi_items.append(item)
        if row["in_kosdaq150"]:
            kosdaq_items.append(item)

    return WeeklyChangeReport(
        date=event_row["last_trading_day"],
        year=event_row["year"],
        month=event_row["month"],
        week_of_month=event_row["week_of_month"],
        week_num=event_row["week"],
        date_range=_event_date_range(event_row),
        items=all_items,
        kospi_200_items=kospi_items,
        kosdaq_150_items=kosdaq_items,
        is_monthly=is_monthly,
    )
