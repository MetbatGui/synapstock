"""{year}.db(stocks 테이블, new_stock_crawler 발행)에서 신규상장 종목을
조회하는 순수 함수 모음.

스키마는 new_stock_crawler의 DataFrameMapper.COLUMN_MAPPING을 그대로 따른다
(한글 컬럼명, pandas to_sql로 동적 생성 - 고정 DDL 없음. 종목명 단일 PK).
"""

import sqlite3
from pathlib import Path


def fetch_listings(db_path: Path) -> list[dict]:
    """stocks 테이블 전체 행을 한글 컬럼명 그대로 dict 리스트로 반환한다."""
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM stocks").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
