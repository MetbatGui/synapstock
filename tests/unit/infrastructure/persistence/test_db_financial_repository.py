"""DbFinancialRepository 유닛 테스트 (TDD: 구현보다 먼저 작성).

FinancialRepository 포트 계약(load_all/get_latest_quarter/get_all_quarters/
get_last_modified_time)을 SQLite SSOT 구독으로 구현한다. 다운로드는 별도
비동기 동기화 단계(container 부팅 시 1회)가 이미 끝낸 뒤라고 가정하고, 이
클래스 자체는 로컬 파일만 동기적으로 읽는다(FinancialService가 동기 호출).
"""
import sqlite3
from pathlib import Path

import pytest

from evenezer.domain.financials.models import FinancialMetric
from evenezer.infrastructure.persistence.db_financial_repository import DbFinancialRepository

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
        detail_type="연결", revenue=1000, operating_profit=100, net_income=50, rcept_no="r1"):
    return (corp_code, corp_name, year, division, quarter, detail_type,
            revenue, operating_profit, net_income, rcept_no)


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "financial_statements.db"


def test_load_all_returns_empty_when_db_not_downloaded_yet(tmp_path):
    repo = DbFinancialRepository(str(tmp_path / "missing.db"))
    assert repo.load_all(FinancialMetric.REVENUE) == []


def test_load_all_returns_financial_statements(db_path):
    make_db(db_path, rows=[row()])
    repo = DbFinancialRepository(str(db_path))

    statements = repo.load_all(FinancialMetric.REVENUE)

    assert len(statements) == 1
    assert statements[0].stock_name == "삼성전자"
    assert statements[0].values == {"2026.1Q": 1000}


def test_get_all_quarters_returns_latest_first(db_path):
    make_db(db_path, rows=[
        row(year=2025, quarter="4Q"),
        row(year=2026, quarter="1Q"),
    ])
    repo = DbFinancialRepository(str(db_path))

    quarters = repo.get_all_quarters(FinancialMetric.REVENUE)

    assert quarters == ["2026.1Q", "2025.4Q"]


def test_get_all_quarters_excludes_quarters_with_no_actual_data(db_path):
    """실 Drive 데이터로 확인함: 아직 공시가 안 들어온 미래 분기도 회사별 '자리표시'
    행(모든 값이 NULL, rcept_no도 NULL)이 미리 만들어져 있다. 이런 분기를 "가용
    분기"에 포함시키면 get_latest_quarter()가 데이터가 하나도 없는 분기를 반환해
    화면이 텅 비게 된다."""
    make_db(db_path, rows=[
        row(year=2026, quarter="1Q", revenue=1000),
        row(year=2026, quarter="2Q", revenue=None, operating_profit=None, net_income=None, rcept_no=None),
    ])
    repo = DbFinancialRepository(str(db_path))

    assert repo.get_all_quarters(FinancialMetric.REVENUE) == ["2026.1Q"]
    assert repo.get_latest_quarter(FinancialMetric.REVENUE) == "2026.1Q"


def test_get_latest_quarter_returns_first_of_all_quarters(db_path):
    make_db(db_path, rows=[row(year=2025, quarter="4Q"), row(year=2026, quarter="1Q")])
    repo = DbFinancialRepository(str(db_path))

    assert repo.get_latest_quarter(FinancialMetric.REVENUE) == "2026.1Q"


def test_get_latest_quarter_empty_when_no_data(tmp_path):
    repo = DbFinancialRepository(str(tmp_path / "missing.db"))
    assert repo.get_latest_quarter(FinancialMetric.REVENUE) == ""


def test_get_last_modified_time_reflects_local_file_mtime(db_path):
    make_db(db_path, rows=[row()])
    repo = DbFinancialRepository(str(db_path))

    assert repo.get_last_modified_time() > 0


def test_get_last_modified_time_zero_when_missing(tmp_path):
    repo = DbFinancialRepository(str(tmp_path / "missing.db"))
    assert repo.get_last_modified_time() == 0.0
