"""db/{year}.db(cohort_stocks + price_history, ceiling-tracker 발행) 조회 함수 테스트.

TDD: 이 테스트를 먼저 작성하고 ceiling_db_query.py는 아직 없다(빨강 확인 후 구현).
스키마는 ceiling-tracker/src/infrastructure/sqlite_repository.py의 _SCHEMA를
그대로 따른다 - cohort_date/price_date는 date.isoformat()(YYYY-MM-DD, 대시 있음).
price_history는 cohort_date 자신의 가격을 담지 않는다(그건 cohort_stocks.initial_price) -
ceiling-tracker의 _rows_to_cohorts에 있는 `if price_date != cohort_date` 규칙 그대로.
"""
import sqlite3
from pathlib import Path

import pytest

from evenezer.infrastructure.persistence.ceiling_db_query import fetch_cohort_report, list_cohort_dates


def make_db(path: Path, cohort_stocks: list[tuple], price_history: list[tuple]) -> None:
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
def db_path(tmp_path):
    return tmp_path / "2026.db"


def test_fetch_cohort_report_returns_none_when_cohort_not_found(db_path):
    make_db(db_path, cohort_stocks=[], price_history=[])

    assert fetch_cohort_report(db_path, "2026-08-28") is None


def test_fetch_cohort_report_includes_initial_price_as_first_date_slot(db_path):
    """D+0(cohort_date 당일)은 price_history가 아니라 initial_price에서 온다."""
    make_db(
        db_path,
        cohort_stocks=[("2026-08-28", "005930", "삼성전자", "신규", 70000)],
        price_history=[("2026-08-28", "005930", "2026-08-31", 75000)],
    )

    report = fetch_cohort_report(db_path, "2026-08-28")

    assert report["dates"] == ["08-28", "08-31"]
    assert report["items"][0]["closing_prices"] == [70000, 75000]


def test_fetch_cohort_report_maps_new_high_status_and_names(db_path):
    make_db(
        db_path,
        cohort_stocks=[("2026-08-28", "005930", "삼성전자", "역사적신고가", 70000)],
        price_history=[],
    )

    report = fetch_cohort_report(db_path, "2026-08-28")

    item = report["items"][0]
    assert item["stock_code"] == "005930"
    assert item["stock_name"] == "삼성전자"
    assert item["new_high_status"] == "역사적신고가"
    assert report["dates"] == ["08-28"]


def test_fetch_cohort_report_forward_fills_missing_price_date_for_one_stock(db_path):
    """한 종목만 특정 날짜 price_history가 없으면(거래정지 등) 직전 값으로 채운다
    (ceiling-tracker 엑셀 파서의 forward-fill 규칙과 동일하게 맞춘다)."""
    make_db(
        db_path,
        cohort_stocks=[
            ("2026-08-28", "005930", "삼성전자", "", 70000),
            ("2026-08-28", "000660", "SK하이닉스", "", 100000),
        ],
        price_history=[
            ("2026-08-28", "005930", "2026-08-31", 75000),
            ("2026-08-28", "005930", "2026-09-01", 76000),
            ("2026-08-28", "000660", "2026-08-31", 105000),
            # 000660은 2026-09-01 데이터 없음 (거래정지 가정)
        ],
    )

    report = fetch_cohort_report(db_path, "2026-08-28")

    hynix = next(it for it in report["items"] if it["stock_code"] == "000660")
    assert hynix["closing_prices"] == [100000, 105000, 105000]  # 마지막 값 forward-fill


def test_fetch_cohort_report_multiple_stocks_share_date_axis(db_path):
    make_db(
        db_path,
        cohort_stocks=[
            ("2026-08-28", "005930", "삼성전자", "", 70000),
            ("2026-08-28", "000660", "SK하이닉스", "", 100000),
        ],
        price_history=[
            ("2026-08-28", "005930", "2026-08-31", 75000),
            ("2026-08-28", "000660", "2026-08-31", 105000),
        ],
    )

    report = fetch_cohort_report(db_path, "2026-08-28")

    assert len(report["items"]) == 2
    assert report["dates"] == ["08-28", "08-31"]


def test_list_cohort_dates_returns_distinct_sorted_dates(db_path):
    make_db(
        db_path,
        cohort_stocks=[
            ("2026-08-28", "005930", "삼성전자", "", 70000),
            ("2026-08-27", "000660", "SK하이닉스", "", 100000),
        ],
        price_history=[],
    )

    assert list_cohort_dates(db_path) == ["2026-08-27", "2026-08-28"]


def test_list_cohort_dates_empty_db_returns_empty_list(db_path):
    make_db(db_path, cohort_stocks=[], price_history=[])

    assert list_cohort_dates(db_path) == []
