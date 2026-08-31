"""{year}.db(stocks 테이블, new_stock_crawler 발행) 조회 함수 테스트 (TDD).

스키마는 new_stock_crawler의 DataFrameMapper.COLUMN_MAPPING을 그대로 따른다
(한글 컬럼명, pandas to_sql로 동적 생성 - 고정 DDL 없음).
"""
import sqlite3
from pathlib import Path

import pytest

from evenezer.infrastructure.persistence.new_listing_db_query import fetch_listings

COLUMNS = [
    "종목명", "시장구분", "업종", "매출액(백만원)", "법인세비용차감전(백만원)",
    "순이익(백만원)", "자본금(백만원)", "총공모주식수", "액면가", "희망공모가액",
    "확정공모가", "공모금액(백만원)", "주간사", "상장일", "기관경쟁률",
    "우리사주조합", "기관투자자", "일반청약자", "유통가능물량(주)", "유통가능물량(%)",
    "시가", "고가", "저가", "종가", "수익률(%)",
]


def make_db(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    placeholders = ",".join("?" for _ in COLUMNS)
    col_list = ",".join(f'"{c}"' for c in COLUMNS)
    conn.execute(f"CREATE TABLE stocks ({col_list})")
    for row in rows:
        values = [row.get(c) for c in COLUMNS]
        conn.execute(f"INSERT INTO stocks VALUES ({placeholders})", values)
    conn.commit()
    conn.close()


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "2026.db"


def test_fetch_listings_returns_empty_for_empty_table(db_path):
    make_db(db_path, rows=[])
    assert fetch_listings(db_path) == []


def test_fetch_listings_returns_all_rows_as_dicts_with_korean_keys(db_path):
    make_db(
        db_path,
        rows=[
            {
                "종목명": "삼성전자", "시장구분": "코스피", "업종": "전자", "상장일": "2026-01-15",
                "확정공모가": 70000, "액면가": 100, "기관경쟁률": 1234.5,
            }
        ],
    )

    rows = fetch_listings(db_path)

    assert len(rows) == 1
    assert rows[0]["종목명"] == "삼성전자"
    assert rows[0]["상장일"] == "2026-01-15"
    assert rows[0]["확정공모가"] == 70000
    assert rows[0]["기관경쟁률"] == 1234.5


def test_fetch_listings_returns_multiple_rows(db_path):
    make_db(
        db_path,
        rows=[
            {"종목명": "삼성전자", "상장일": "2026-01-15"},
            {"종목명": "SK하이닉스", "상장일": "2026-02-01"},
        ],
    )

    rows = fetch_listings(db_path)

    assert {r["종목명"] for r in rows} == {"삼성전자", "SK하이닉스"}
