"""market_data_{year}.db(netbuy + price_info, krx-auto-crawling 발행)에서
수급 순위를 조회하는 순수 함수 모음.

우선순위/텍스트는 krx-auto-crawling의 HighPriceIndicatorService와 동일하게 맞춘다
(역사적 신고가 > 역사적 근접 > 52주 신고가 > 52주 근접, 근접 판정은 90% 이상).
"""

import sqlite3
from pathlib import Path

# mindmap 도메인(SupplySubject) -> 생산자 DB의 investor 컬럼 값
_INVESTOR_MAP = {
    "FOREIGN": "foreigner",
    "INSTITUTION": "institutions",
}

_NEAR_THRESHOLD = 0.9


def _to_db_date(date_str: str) -> str:
    """mindmap 도메인 날짜(YYYY-MM-DD)를 생산자 DB의 date_str 포맷(YYYYMMDD)으로 변환한다.

    실 데이터로 검증하다 발견함 - krx-auto-crawling이 발행하는 netbuy/price_info의
    date_str은 대시 없는 YYYYMMDD다. mindmap 도메인 모델은 전부 YYYY-MM-DD를 쓰므로
    쿼리 경계에서 반드시 변환해야 한다.
    """
    return date_str.replace("-", "")


def _from_db_date(db_date_str: str) -> str:
    """생산자 DB의 date_str(YYYYMMDD)을 mindmap 도메인 날짜(YYYY-MM-DD)로 변환한다."""
    return f"{db_date_str[:4]}-{db_date_str[4:6]}-{db_date_str[6:8]}"


def list_dates(db_path: Path) -> list[str]:
    """DB에 존재하는 모든 거래일을 mindmap 도메인 포맷(YYYY-MM-DD)의 오름차순으로 반환한다."""
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        rows = conn.execute("SELECT DISTINCT date_str FROM netbuy ORDER BY date_str").fetchall()
        return [_from_db_date(r[0]) for r in rows]
    finally:
        conn.close()


def _high_price_type(close_price: float, high_52w: float | None, all_time_high: float | None) -> str | None:
    if all_time_high is not None:
        if close_price >= all_time_high:
            return "역·신"
        if close_price >= all_time_high * _NEAR_THRESHOLD:
            return "역·근"
    if high_52w is not None:
        if close_price >= high_52w:
            return "52·신"
        if close_price >= high_52w * _NEAR_THRESHOLD:
            return "52·근"
    return None


def fetch_ranking_rows(db_path: Path, market: str, subject: str, date_str: str, limit: int = 30) -> list[dict]:
    """(market, subject, date_str) 조합의 순위표를 rank 오름차순으로 반환한다.

    market은 "KOSPI"/"KOSDAQ", subject는 "FOREIGN"/"INSTITUTION"(mindmap
    도메인 값), date_str은 "YYYY-MM-DD"(mindmap 도메인 포맷) 그대로 받는다 -
    DB 내부 포맷(YYYYMMDD) 변환은 이 함수가 책임진다.

    Returns:
        list[dict]: rank/stock_code/stock_name/net_buy_amount/high_price_type.
    """
    investor = _INVESTOR_MAP[subject]
    db_date_str = _to_db_date(date_str)
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT n.rank, n.stock_code, n.stock_name, n.net_buy_amount,
                   p.close_price, p.high_52w, p.all_time_high
            FROM netbuy n
            LEFT JOIN price_info p ON p.date_str = n.date_str AND p.stock_code = n.stock_code
            WHERE n.date_str = ? AND n.market = ? AND n.investor = ?
            ORDER BY n.rank ASC
            LIMIT ?
            """,
            (db_date_str, market, investor, limit),
        ).fetchall()

        result = []
        for r in rows:
            high_price_type = None
            if r["close_price"] is not None:
                high_price_type = _high_price_type(r["close_price"], r["high_52w"], r["all_time_high"])
            result.append(
                {
                    "rank": r["rank"],
                    "stock_code": r["stock_code"],
                    "stock_name": r["stock_name"],
                    "net_buy_amount": r["net_buy_amount"],
                    "high_price_type": high_price_type,
                }
            )
        return result
    finally:
        conn.close()
