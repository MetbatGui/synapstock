import io
import pandas as pd
import pytest
from synapstock.infrastructure.parsers.excel import DisclosureParser
from synapstock.domain.statistics.models import PaidInCapitalIncrease

def test_parse_paid_in_capital_increase_with_real_example():
    """사용자가 제공한 '대한광통신' 실사 데이터를 활용하여 유상증자 파싱을 검증합니다."""
    
    # 1. 예시 데이터 설정 (탭 구분 데이터를 딕셔너리 리스트로 변환)
    # 칼럼 순서: 일자, 종목명, 기재정정여부, 유상증자공시일, 접수번호, 상위접수번호, 신주발행주식수, 1주당 액면가, 
    # 증자전 발행주식총수, 시설자금, 운영자금, 타법인증권, 기타자금, 증자방식, 신주의 발행가액, 발행확정가액, 
    # 신주배정기준일, 1주당 신주배정주식수, 청약예정일, 납입일, 신주상장일, 이사회결의일, 최초공시일
    
    columns = [
        "일자", "종목명", "기재정정여부", "유상증자공시일", "접수번호", "상위접수번호", 
        "신주발행주식수", "1주당 액면가", "증자전 발행주식총수", "시설자금", "운영자금", 
        "타법인증권", "기타자금", "증자방식", "신주의 발행가액", "발행확정가액", 
        "신주배정기준일", "1주당 신주배정주식수", "청약예정일", "납입일", 
        "신주상장일", "이사회결의일", "최초공시일"
    ]
    
    example_row = [
        "2026-01-07", "대한광통신", "[기재정정]", "2026-01-07", "20260107000372", "20251205000556",
        23500000, 500, 131985660, 3500000000, 35380000000, 0, 0,
        "주주배정후 실권주 일반공모", 0, None, "2026-01-09", 0.1780496456,
        "2026-02-25", "2026-03-06", None, "2025-12-05", "2025-12-05"
    ]
    
    df = pd.DataFrame([example_row], columns=columns)
    
    # 2. 엑셀 바이너리 생성
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    content = output.getvalue()
    
    # 3. 파싱 수행
    parser = DisclosureParser()
    results = parser.parse_paid_in_capital_increase(content)
    
    # 4. 검증
    assert len(results) == 1
    item = results[0]
    
    assert item.name == "대한광통신"
    assert item.date == "2026-01-07"
    assert item.is_correction is True  # '[기재정정]' 포함 시 True여야 함
    assert item.new_shares == 23500000
    assert item.fund_facility == 3500000000
    assert item.fund_operation == 35380000000
    assert item.method == "주주배정후 실권주 일반공모"
    assert item.shares_per_old == pytest.approx(0.1780496456)
    assert item.total_fund == 3500000000 + 35380000000
    assert item.initial_disclosure_date == "2025-12-05"

def test_parse_paid_in_capital_increase_with_dirty_data():
    """숫자에 콤마나 단위가 포함된 경우 등 지저분한 데이터 파싱을 검증합니다."""
    columns = [
        "일자", "종목명", "기재정정여부", "유상증자공시일", "접수번호", "신주발행주식수", 
        "시설자금", "운영자금", "1주당 신주배정주식수"
    ]
    
    # 콤마, 원, 주 등의 단위가 섞인 데이터
    example_row = [
        "2026-01-07", "테스트종목", "N", "2026-01-07", "123", "10,000,000주",
        "5,000,000,000원", "1,200,500", "0.15%"
    ]
    
    df = pd.DataFrame([example_row], columns=columns)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    content = output.getvalue()
    
    parser = DisclosureParser()
    results = parser.parse_paid_in_capital_increase(content)
    
    assert len(results) == 1
    item = results[0]
    assert item.new_shares == 10000000
    assert item.fund_facility == 5000000000
    assert item.fund_operation == 1200500
    # % 문자가 있으면 float 변환 시 주의가 필요할 수도 있으나, 현재 정규식은 숫자와 점만 추출함
    # "0.15%" -> "0.15" -> 0.15
    assert item.shares_per_old == 0.15

def test_parse_paid_in_capital_increase_multi_sheets():
    """여러 시트(연도별)에 데이터가 나누어져 있을 때 모든 데이터를 파싱하는지 검증합니다."""
    columns = ["일자", "종목명", "기재정정여부", "유상증자공시일", "접수번호", "신주발행주식수"]
    
    # 2023 시트 데이터
    row_2023 = ["2023-01-01", "2023종목", "N", "2023-01-01", "101", 100]
    df_2023 = pd.DataFrame([row_2023], columns=columns)
    
    # 2024 시트 데이터
    row_2024 = ["2024-01-01", "2024종목", "N", "2024-01-01", "102", 200]
    df_2024 = pd.DataFrame([row_2024], columns=columns)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_2023.to_excel(writer, sheet_name='2023', index=False)
        df_2024.to_excel(writer, sheet_name='2024', index=False)
    content = output.getvalue()
    
    parser = DisclosureParser()
    results = parser.parse_paid_in_capital_increase(content)
    
    # 모든 시트의 데이터 합계 확인
    assert len(results) == 2
    names = [item.name for item in results]
    assert "2023종목" in names
    assert "2024종목" in names
