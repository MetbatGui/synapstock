"""db/financial_statements.db(companies+financials, dart-fss-extractor 발행) 조회
함수 테스트 (TDD).

병합 규칙(연결 우선/개별 보완, 셀 단위)은 dart-fss-extractor의
financial_data_export_service.py가 이미 쓰고 있는 combine_first 규칙을
그대로 복제한다 - 새로 정하지 않았다.
"""
import sqlite3
from pathlib import Path

import pytest

from evenezer.infrastructure.persistence.financial_db_query import (
    fetch_statements,
    list_quarters,
)

COLUMNS = [
    "corp_code", "corp_name", "year", "division", "quarter", "detail_type",
    "revenue", "operating_profit", "net_income", "rcept_no",
]


def make_db(path: Path, rows: list[tuple]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    col_list = ",".join(COLUMNS)
    conn.execute(f"CREATE TABLE financials ({col_list})")
    placeholders = ",".join("?" for _ in COLUMNS)
    conn.executemany(f"INSERT INTO financials VALUES ({placeholders})", rows)
    conn.commit()
    conn.close()


def row(corp_code="005930", corp_name="삼성전자", year=2026, division="분기", quarter="1Q",
        detail_type="연결", revenue=None, operating_profit=None, net_income=None, rcept_no="r1"):
    return (corp_code, corp_name, year, division, quarter, detail_type,
            revenue, operating_profit, net_income, rcept_no)


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "financial_statements.db"


def test_fetch_statements_uses_consolidated_value_when_present(db_path):
    make_db(db_path, rows=[
        row(detail_type="연결", revenue=1000),
        row(detail_type="개별", revenue=900),
    ])

    statements = fetch_statements(db_path, "REVENUE")

    assert len(statements) == 1
    assert statements[0]["stock_name"] == "삼성전자"
    assert statements[0]["values"] == {"2026.1Q": 1000}


def test_fetch_statements_falls_back_to_individual_when_consolidated_missing(db_path):
    """연결 행 자체가 없는 회사(단일법인 등)는 개별 값을 그대로 쓴다."""
    make_db(db_path, rows=[row(detail_type="개별", revenue=900)])

    statements = fetch_statements(db_path, "REVENUE")

    assert statements[0]["values"] == {"2026.1Q": 900}


def test_fetch_statements_falls_back_per_cell_when_consolidated_value_is_null(db_path):
    """연결 행은 있지만 특정 지표 값이 NULL이면 그 지표만 개별로 채운다(combine_first
    셀 단위 규칙 - 회사/행 단위 통짜 선택이 아님)."""
    make_db(db_path, rows=[
        row(detail_type="연결", revenue=1000, operating_profit=None),
        row(detail_type="개별", revenue=900, operating_profit=200),
    ])

    revenue_statements = fetch_statements(db_path, "REVENUE")
    profit_statements = fetch_statements(db_path, "OPERATING_PROFIT")

    assert revenue_statements[0]["values"] == {"2026.1Q": 1000}  # 연결 값 유지
    assert profit_statements[0]["values"] == {"2026.1Q": 200}  # 연결 NULL -> 개별로 채움


def test_fetch_statements_includes_values_regardless_of_rcept_no(db_path):
    """rcept_no는 신뢰성 신호로 쓰지 않는다 - 실 Drive 데이터 확인 결과 정상 수집된
    값도 대부분(2533개 중 86개 제외) rcept_no가 비어있어서, 이 컬럼으로 필터링하면
    진짜 데이터 대부분이 사라진다."""
    make_db(db_path, rows=[row(quarter="1Q", revenue=1000, rcept_no=None)])

    statements = fetch_statements(db_path, "REVENUE")

    assert statements[0]["values"] == {"2026.1Q": 1000}


def test_fetch_statements_excludes_annual_division(db_path):
    """mindmap 도메인은 분기 키("YYYY.NQ")만 쓴다 - "연간" 구분 행은 제외한다."""
    make_db(db_path, rows=[
        row(division="분기", quarter="1Q", revenue=1000),
        row(division="연간", quarter="연간", revenue=4000),
    ])

    statements = fetch_statements(db_path, "REVENUE")

    assert statements[0]["values"] == {"2026.1Q": 1000}


def test_fetch_statements_groups_multiple_quarters_and_companies(db_path):
    make_db(db_path, rows=[
        row(corp_code="005930", corp_name="삼성전자", quarter="1Q", revenue=1000),
        row(corp_code="005930", corp_name="삼성전자", quarter="2Q", revenue=1100),
        row(corp_code="000660", corp_name="SK하이닉스", quarter="1Q", revenue=500),
    ])

    statements = fetch_statements(db_path, "REVENUE")

    by_name = {s["stock_name"]: s["values"] for s in statements}
    assert by_name["삼성전자"] == {"2026.1Q": 1000, "2026.2Q": 1100}
    assert by_name["SK하이닉스"] == {"2026.1Q": 500}


def test_list_quarters_returns_distinct_sorted_quarter_labels(db_path):
    make_db(db_path, rows=[
        row(year=2025, quarter="4Q", revenue=1),
        row(year=2026, quarter="1Q", revenue=1),
        row(year=2026, quarter="1Q", corp_code="000660", revenue=1),  # 중복 - 제외
    ])

    assert list_quarters(db_path) == ["2025.4Q", "2026.1Q"]
