"""db/financial_statements.db(companies+financials, dart-fss-extractor 발행)에서
재무 시계열을 조회하는 순수 함수 모음.

연결(CFS) 우선/개별(OFS) 대체 병합 규칙은 dart-fss-extractor의
financial_data_export_service.py(연결 우선/개별 보완, combine_first)를 그대로
복제한다 - 회사/행 단위 통짜 선택이 아니라 지표(셀) 단위로, 연결 값이 있으면
그 값을, 없으면(NULL) 개별 값으로 채운다.
"""

import sqlite3
from pathlib import Path

_METRIC_COLUMN = {
    "REVENUE": "revenue",
    "OPERATING_PROFIT": "operating_profit",
    "NET_INCOME": "net_income",
}

_CONSOLIDATED = "연결"
_INDIVIDUAL = "개별"


def list_quarters(db_path: Path) -> list[str]:
    """DB에 존재하는 모든 분기 라벨("YYYY.NQ")을 오름차순으로 반환한다."""
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT DISTINCT year, quarter FROM financials WHERE division = '분기'"
        ).fetchall()
    finally:
        conn.close()
    labels = {f"{year}.{quarter}" for year, quarter in rows}
    return sorted(labels)


def fetch_statements(db_path: Path, metric: str) -> list[dict]:
    """지정된 지표의 회사별 분기 시계열을 연결 우선/개별 보완으로 병합해 반환한다.

    Returns:
        list[dict]: [{"stock_name": str, "values": {"YYYY.NQ": float, ...}}, ...]
    """
    column = _METRIC_COLUMN[metric]
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            f"""
            SELECT corp_code, corp_name, year, quarter, detail_type, {column} AS value
            FROM financials
            WHERE division = '분기'
            """
        ).fetchall()
    finally:
        conn.close()

    # (corp_code, year, quarter) -> {"corp_name": str, "연결": value|None, "개별": value|None}
    # rcept_no로 필터링하지 않는다 - 실 데이터 확인 결과 정상적으로 수집된 값도
    # 대부분(2533개 중 86개 제외) rcept_no가 비어있어서(수집 경로에 따라 채워지지
    # 않는 필드), 이 컬럼을 신뢰성 신호로 쓸 수 없다. 값 자체의 존재 여부만 본다 -
    # dart-fss-extractor의 daily export도 연도 필터 없이 그대로 내보내므로, 드문드문
    # 먼저 보고되는 분기(결산월이 다른 회사 등)가 섞이는 건 원래 있던 데이터 특성이다.
    merged: dict[tuple, dict] = {}
    for r in rows:
        key = (r["corp_code"], r["year"], r["quarter"])
        entry = merged.setdefault(key, {"corp_name": r["corp_name"]})
        entry[r["detail_type"]] = r["value"]

    by_company: dict[str, dict[str, float]] = {}
    for (corp_code, year, quarter), entry in merged.items():
        value = entry.get(_CONSOLIDATED)
        if value is None:
            value = entry.get(_INDIVIDUAL)
        if value is None:
            continue
        quarter_key = f"{year}.{quarter}"
        by_company.setdefault(entry["corp_name"], {})[quarter_key] = value

    return [{"stock_name": name, "values": values} for name, values in by_company.items()]
