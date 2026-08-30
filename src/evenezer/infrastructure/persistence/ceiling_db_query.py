"""db/{year}.db(cohort_stocks + price_history, ceiling-tracker 발행)에서
상한가 코호트 리포트를 조회하는 순수 함수 모음.

날짜는 ceiling-tracker와 동일하게 date.isoformat()(YYYY-MM-DD, 대시 있음) 그대로
쓴다 - 별도 포맷 변환이 필요 없다.

D+0(cohort_date 당일) 가격은 price_history가 아니라 cohort_stocks.initial_price에
있다(ceiling-tracker의 _rows_to_cohorts가 `price_date != cohort_date`인 행만
price_history로 취급하는 것과 동일한 규칙). 종목별로 특정 날짜의 price_history가
없으면(거래정지 등) 직전 값으로 forward-fill한다 - ceiling-tracker의 엑셀 파서가
쓰던 것과 동일한 결측 처리 규칙을 그대로 따른다.
"""

import sqlite3
from pathlib import Path


def list_cohort_dates(db_path: Path) -> list[str]:
    """DB에 존재하는 모든 cohort_date를 오름차순으로 반환한다."""
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        rows = conn.execute("SELECT DISTINCT cohort_date FROM cohort_stocks ORDER BY cohort_date").fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def fetch_cohort_report(db_path: Path, cohort_date: str) -> dict | None:
    """지정된 cohort_date의 코호트를 조립해 반환한다.

    Returns:
        dict | None: {"dates": ["MM-DD", ...], "items": [{"stock_code",
            "stock_name", "new_high_status", "closing_prices"}, ...]}.
            해당 cohort_date에 코호트가 없으면 None.
    """
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        cs_rows = conn.execute(
            "SELECT stock_code, stock_name, new_high_status, initial_price "
            "FROM cohort_stocks WHERE cohort_date = ? ORDER BY stock_code",
            (cohort_date,),
        ).fetchall()
        if not cs_rows:
            return None

        ph_rows = conn.execute(
            "SELECT stock_code, price_date, price FROM price_history "
            "WHERE cohort_date = ? ORDER BY price_date",
            (cohort_date,),
        ).fetchall()

        ph_by_stock: dict[str, dict[str, int]] = {}
        all_dates = {cohort_date}
        for r in ph_rows:
            ph_by_stock.setdefault(r["stock_code"], {})[r["price_date"]] = r["price"]
            all_dates.add(r["price_date"])
        sorted_dates = sorted(all_dates)

        items = []
        for cs in cs_rows:
            prices: list[int] = []
            last = cs["initial_price"]
            stock_prices = ph_by_stock.get(cs["stock_code"], {})
            for d in sorted_dates:
                if d == cohort_date:
                    val = cs["initial_price"]
                else:
                    val = stock_prices.get(d, last)
                prices.append(val)
                last = val
            items.append(
                {
                    "stock_code": cs["stock_code"],
                    "stock_name": cs["stock_name"],
                    "new_high_status": cs["new_high_status"],
                    "closing_prices": prices,
                }
            )

        return {
            "dates": [f"{d[5:7]}-{d[8:10]}" for d in sorted_dates],
            "items": items,
        }
    finally:
        conn.close()
