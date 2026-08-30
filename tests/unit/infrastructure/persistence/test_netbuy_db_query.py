import sqlite3
from pathlib import Path

import pytest

from evenezer.infrastructure.persistence.netbuy_db_query import fetch_ranking_rows, list_dates


def make_db(path: Path, netbuy_rows: list[tuple], price_rows: list[tuple]) -> None:
    """netbuy_rows/price_rows의 date_str은 생산자 DB의 실제 포맷(YYYYMMDD, 대시 없음)으로
    넣는다 - 실 Drive 데이터로 검증하다 이 포맷을 확인했다(대시가 있는 mindmap 도메인
    포맷이 아님)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE netbuy (date_str TEXT, market TEXT, investor TEXT, rank INTEGER, "
        "stock_code TEXT, stock_name TEXT, net_buy_amount INTEGER, "
        "PRIMARY KEY (date_str, market, investor, rank))"
    )
    conn.execute(
        "CREATE TABLE price_info (date_str TEXT, stock_code TEXT, stock_name TEXT, "
        "close_price REAL, high_52w REAL, all_time_high REAL, "
        "PRIMARY KEY (date_str, stock_code))"
    )
    conn.executemany("INSERT INTO netbuy VALUES (?,?,?,?,?,?,?)", netbuy_rows)
    conn.executemany("INSERT INTO price_info VALUES (?,?,?,?,?,?)", price_rows)
    conn.commit()
    conn.close()


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "market_data_2026.db"


def test_fetch_ranking_rows_accepts_dashed_date_and_queries_undashed_db(db_path):
    """mindmap 도메인은 YYYY-MM-DD를 쓰지만 생산자 DB는 YYYYMMDD를 쓴다 - 쿼리
    함수가 경계에서 변환해야 한다(실 Drive 데이터로 검증하다 발견한 버그)."""
    make_db(
        db_path,
        netbuy_rows=[("20260828", "KOSPI", "foreigner", 1, "005930", "삼성전자", 1000)],
        price_rows=[],
    )

    rows = fetch_ranking_rows(db_path, market="KOSPI", subject="FOREIGN", date_str="2026-08-28")

    assert len(rows) == 1
    assert rows[0]["stock_name"] == "삼성전자"


def test_fetch_ranking_rows_orders_by_rank_and_filters_combo(db_path):
    make_db(
        db_path,
        netbuy_rows=[
            ("20260828", "KOSPI", "foreigner", 2, "000020", "동화약품", 500),
            ("20260828", "KOSPI", "foreigner", 1, "005930", "삼성전자", 1000),
            ("20260828", "KOSPI", "institutions", 1, "005930", "삼성전자", 700),  # 다른 조합 - 제외
            ("20260827", "KOSPI", "foreigner", 1, "005930", "삼성전자", 900),  # 다른 날짜 - 제외
        ],
        price_rows=[],
    )

    rows = fetch_ranking_rows(db_path, market="KOSPI", subject="FOREIGN", date_str="2026-08-28")

    assert [r["rank"] for r in rows] == [1, 2]
    assert rows[0]["stock_name"] == "삼성전자"
    assert rows[0]["net_buy_amount"] == 1000


def test_fetch_ranking_rows_respects_limit(db_path):
    rows_in = [
        ("20260828", "KOSPI", "foreigner", i, f"{i:06d}", f"종목{i}", 100 - i) for i in range(1, 6)
    ]
    make_db(db_path, netbuy_rows=rows_in, price_rows=[])

    rows = fetch_ranking_rows(db_path, market="KOSPI", subject="FOREIGN", date_str="2026-08-28", limit=3)

    assert len(rows) == 3
    assert [r["rank"] for r in rows] == [1, 2, 3]


def test_fetch_ranking_rows_maps_institution_subject(db_path):
    make_db(
        db_path,
        netbuy_rows=[("20260828", "KOSDAQ", "institutions", 1, "086520", "에코프로", 300)],
        price_rows=[],
    )

    rows = fetch_ranking_rows(db_path, market="KOSDAQ", subject="INSTITUTION", date_str="2026-08-28")

    assert len(rows) == 1
    assert rows[0]["stock_name"] == "에코프로"


@pytest.mark.parametrize(
    "close_price,high_52w,all_time_high,expected",
    [
        (100.0, 100.0, 150.0, "52·신"),  # 52주 신고가만 달성
        (100.0, 90.0, 100.0, "역·신"),  # 역대 신고가 달성 (우선순위 최상)
        (91.0, 100.0, 100.0, "역·근"),  # 역대 신고가 90% 이상 근접
        (85.0, 90.0, 200.0, "52·근"),  # 52주 신고가 90% 이상 근접
        (50.0, 100.0, 200.0, None),  # 어느 것도 해당 없음
    ],
)
def test_fetch_ranking_rows_high_price_type_priority(db_path, close_price, high_52w, all_time_high, expected):
    """우선순위: 역사적 신고가 > 역사적 근접 > 52주 신고가 > 52주 근접 (근접=90% 이상)."""
    make_db(
        db_path,
        netbuy_rows=[("20260828", "KOSPI", "foreigner", 1, "005930", "삼성전자", 1000)],
        price_rows=[("20260828", "005930", "삼성전자", close_price, high_52w, all_time_high)],
    )

    rows = fetch_ranking_rows(db_path, market="KOSPI", subject="FOREIGN", date_str="2026-08-28")

    assert rows[0]["high_price_type"] == expected


def test_fetch_ranking_rows_missing_price_info_gives_none_high_price_type(db_path):
    make_db(
        db_path,
        netbuy_rows=[("20260828", "KOSPI", "foreigner", 1, "005930", "삼성전자", 1000)],
        price_rows=[],
    )

    rows = fetch_ranking_rows(db_path, market="KOSPI", subject="FOREIGN", date_str="2026-08-28")

    assert rows[0]["high_price_type"] is None


def test_list_dates_returns_distinct_sorted_dashed_dates(db_path):
    """list_dates는 생산자 DB의 YYYYMMDD를 mindmap 도메인 포맷(YYYY-MM-DD)으로 변환해 반환한다."""
    make_db(
        db_path,
        netbuy_rows=[
            ("20260828", "KOSPI", "foreigner", 1, "005930", "삼성전자", 1000),
            ("20260827", "KOSPI", "foreigner", 1, "005930", "삼성전자", 900),
            ("20260828", "KOSDAQ", "institutions", 1, "086520", "에코프로", 300),
        ],
        price_rows=[],
    )

    assert list_dates(db_path) == ["2026-08-27", "2026-08-28"]
