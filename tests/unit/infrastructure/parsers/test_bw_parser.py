import io

import pandas as pd

from evenezer.infrastructure.parsers.excel import DisclosureParser


def test_parse_bond_with_warrants_real_example():
    # 사용자 제공 예시 데이터 (오텍)
    # 컬럼 구조: 공시일 상호 기재정정여부 회차 종류 권면총액(1) 권면총액(2) 시설 운영 영업양수 타법인 채무 기타 만기일 발행방법 비율 행사가액 인수주식수 총수대비비율 행사시작일 행사종료일 청약일 납입일 결의일 접수번호 상위접수번호 최초공시일
    data = {
        "공시일": ["2026-01-05"],
        "상호": ["오텍"],
        "기재정정여부": ["[기재정정]"],
        "회차": ["13"],
        "종류": ["무기명식 이권부 무보증 공모 분리형 신주인수권부사채"],
        "사채의 권면(전자등록)총액": [20000000000],
        "권면(전자등록)총액": [20000000000],
        "시설자금": [None],
        "운영자금": [None],
        "영업양수자금": [None],
        "타법인증권": [20000000000],
        "채무상환자금": [None],
        "기타자금": [None],
        "사채의 만기일": ["2031-01-12"],
        "사채발행방법": ["공모"],
        "신주인수권 비율": [100],
        "행사가액": [1881],
        "행사에 따라 발행할 주식수": [10632642],
        "주식총수 대비 비율": [44.5],
        "권리행사기간 시작일": ["2026-02-12"],
        "권리행사기간 종료일": ["2030-12-12"],
        "청약일": ["2026-01-07"],
        "납입일": ["2026-01-12"],
        "이사회결의일": ["2025-12-12"],
        "접수번호": ["20260105000068"],
        "상위접수번호": ["20251212000428"],
        "최초공시일": ["2025-12-12"]
    }

    df = pd.DataFrame(data)

    # 엑셀 바이너리 시뮬레이션
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name="Sheet1")
    content = output.getvalue()

    parser = DisclosureParser()
    items = parser.parse_bond_with_warrants(content)

    assert len(items) == 1
    bw = items[0]
    assert bw.name == "오텍"
    assert bw.bond_round == "13"
    assert bw.is_correction is True
    assert bw.bond_amount == 20000000000
    assert bw.fund_acquisition_sec == 20000000000
    assert bw.total_fund == 20000000000
    assert bw.exercise_price == 1881
    assert bw.warrant_ratio == 100.0
    assert bw.exercise_start_date == "2026-02-12"
    assert bw.exercise_end_date == "2030-12-12"
    assert bw.rcp_no == "20260105000068"
    assert bw.initial_disclosure_date == "2025-12-12"

if __name__ == "__main__":
    test_parse_bond_with_warrants_real_example()
    print("BW Parser Unit Test Passed!")
