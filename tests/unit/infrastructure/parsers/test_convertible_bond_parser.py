import io

import pandas as pd

from evenezer.infrastructure.parsers.excel import DisclosureParser


def test_parse_convertible_bond_with_user_example():
    """사용자가 제공한 '대양금속' 예제 데이터를 활용하여 전환사채 파싱을 검증합니다."""

    # 27개 필드 정의
    columns = [
        "공시일", "상호", "기재정정여부", "회차", "종류",
        "사채의 권면(전자등록)총액", "권면(전자등록)총액",
        "시설자금", "운영자금", "영업양수자금", "타법인증권", "채무상환자금", "기타자금",
        "사채의 만기일", "사채발행방법", "전환비율", "전환가액",
        "전환에 따라 발행할 주식수", "주식총수 대비 비율",
        "전환청구기간시작일", "전환청구기간종료일", "청약일", "납입일",
        "이사회결의일", "접수번호", "상위접수번호", "최초공시일"
    ]

    # 예제 행 데이터 (탭 구분 데이터를 리스트로 변환)
    # 2026-01-02	대양금속	[기재정정]	24	국내 무기명식 이권부 무보증 사모 전환사채
    # 10000000000	10000000000	(시설) (운영30억) (영업양수) (타법인70억) (채무) (기타)
    # 2029-02-04	사모	100	1304	7668711	12.06
    # 2027-02-04	2029-01-04	2026-02-04	2026-02-04	2025-07-30
    # 20260102000248	20251205000362	2025-07-31
    example_row = [
        "2026-01-02", "대양금속", "[기재정정]", "24", "국내 무기명식 이권부 무보증 사모 전환사채",
        10000000000, 10000000000,
        None, 3000000000, None, 7000000000, None, None,
        "2029-02-04", "사모", 100, 1304, 7668711, 12.06,
        "2027-02-04", "2029-01-04", "2026-02-04", "2026-02-04", "2025-07-30",
        "20260102000248", "20251205000362", "2025-07-31"
    ]

    df = pd.DataFrame([example_row], columns=columns)

    # 엑셀 바이너리 생성
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    content = output.getvalue()

    # 파싱 수행
    parser = DisclosureParser()
    results = parser.parse_convertible_bond(content)

    # 검증
    assert len(results) == 1
    item = results[0]

    assert item.name == "대양금속"
    assert item.date == "2026-01-02"
    assert item.is_correction is True
    assert item.bond_round == "24"
    assert item.bond_amount == 10000000000
    assert item.fund_operation == 3000000000
    assert item.fund_acquisition_sec == 7000000000
    assert item.fund_facility == 0
    assert item.issue_method == "사모"
    assert item.conversion_price == 1304
    assert item.new_shares == 7668711
    assert item.shares_ratio == 12.06
    assert item.maturity_date == "2029-02-04"
    assert item.exercise_start_date == "2027-02-04"
    assert item.exercise_end_date == "2029-01-04"
    assert item.rcp_no == "20260102000248"
    assert item.parent_rcp_no == "20251205000362"
    assert item.total_fund == 10000000000

def test_parse_convertible_bond_with_dirty_numbers():
    """하이픈(-)이나 콤마가 포함된 숫자 데이터 파싱을 검증합니다."""
    columns = ["상호", "공시일", "권면총액", "시설자금", "운영자금"]
    example_row = ["테스트종목", "2026-01-01", "1,000,000,000", "-", "500,000,000"]

    df = pd.DataFrame([example_row], columns=columns)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    content = output.getvalue()

    parser = DisclosureParser()
    results = parser.parse_convertible_bond(content)

    assert len(results) == 1
    item = results[0]
    assert item.bond_amount == 1000000000
    assert item.fund_facility == 0
    assert item.fund_operation == 500000000
