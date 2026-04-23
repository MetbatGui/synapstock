import io

import pandas as pd
import pytest

from synapstock.infrastructure.parsers.excel.disclosure import DisclosureParser


@pytest.fixture
def parser():
    return DisclosureParser()

def test_parse_paid_in_capital_increase(parser):
    # 유상증자 가상 데이터
    data = {
        "종목명": ["상상인"],
        "기재정정여부": ["N"],
        "유상증자공시일": ["2026-04-16"],
        "접수번호": ["202604160001"],
        "신주발행주식수": [1000000],
        "1주당 액면가": [500],
        "신주의 발행가액": [2000],
        "신주배정기준일": ["2026-05-01"]
    }
    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='2026')

    results = parser.parse_paid_in_capital_increase(output.getvalue())

    assert len(results) == 1
    assert results[0].name == "상상인"
    assert results[0].new_shares == 1000000
    assert results[0].issue_price == 2000

def test_parse_convertible_bond(parser):
    # CB 가상 데이터
    data = {
        "종목명": ["현대차"],
        "회차": ["10회"],
        "권면총액": [50000000000],
        "공시일": ["2026-04-20"],
        "전환가액": [150000],
        "접수번호": ["202604200002"]
    }
    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='CB')

    results = parser.parse_convertible_bond(output.getvalue())

    assert len(results) == 1
    assert results[0].name == "현대차"
    assert results[0].bond_amount == 50000000000
    assert results[0].conversion_price == 150000
