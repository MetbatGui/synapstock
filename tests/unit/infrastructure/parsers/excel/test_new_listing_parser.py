import io

import pandas as pd

from evenezer.infrastructure.parsers.excel.new_listing import NewListingParser


def test_new_listing_parser_with_sample_data():
    # 사용자가 제공한 샘플 데이터 기반의 엑셀 생성
    data = {
        "종목명": ["덕양에너젠"],
        "시장구분": ["코스닥"],
        "업종": ["산소, 질소 및 기타 산업용 가스 제조업"],
        "매출액(백만원)": [137370],
        "법인세비용차감전(백만원)": [4230],
        "순이익(백만원)": [3031],
        "자본금(백만원)": [12395],
        "총공모주식수": [7500000],
        "액면가": [500],
        "희망공모가액": ["8,500 ~ 10,000 원"],
        "확정공모가": [10000],
        "공모금액(백만원)": [75000],
        "주간사": ["NH투자증권,미래에셋증권"],
        "상장일": ["2026.01.30"],
        "기관경쟁률": ["650:1"],
        "유통가능물량(%)": ["32.33%"],
        "시가": [21050],
        "고가": [39500],
        "저가": [20250],
        "종가": [34850],
        "수익률(%)": [248.5]
    }
    df = pd.DataFrame(data)

    # 엑셀 바이너리로 변환
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
    excel_content = output.getvalue()

    parser = NewListingParser()
    results = parser.parse(excel_content)

    assert len(results) == 1
    item = results[0]

    assert item.name == "덕양에너젠"
    assert item.sector == "산소, 질소 및 기타 산업용 가스 제조업"
    assert item.offer_price == 10000
    assert item.lead_manager == "NH투자증권,미래에셋증권"
    assert item.listing_date == "2026.01.30"
    assert item.institutional_competition == 650.0  # '650:1' -> 650.0
    assert item.float_shares_pct == 32.33
    assert item.listing_day_open == 21050
    assert item.listing_day_high == 39500
    assert item.listing_day_low == 20250
    assert item.listing_day_close == 34850
    assert item.listing_day_change_pct == 248.5

def test_new_listing_parser_finds_header_within_15_rows():
    # 헤더가 5행부터 시작하는 경우
    data = [["익명"]*21] * 5  # 쓰레기 데이터
    headers = ["종목명", "상장일", "확정공모가", "기관경쟁률", "유통가능물량(%)", "시가", "고가", "저가", "종가", "수익률(%)"]
    # 필요한 최소 헤더만 채움
    header_row = [""] * 21
    for i, h in enumerate(headers):
        header_row[i] = h
    data.append(header_row)
    data.append(["삼성전자", "2026.04.01", 50000, "1000:1", "10%", 60000, 70000, 55000, 65000, 30.0] + [""]*11)

    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, header=False, sheet_name='Sheet1')
    excel_content = output.getvalue()

    parser = NewListingParser()
    results = parser.parse(excel_content)

    assert len(results) == 1
    assert results[0].name == "삼성전자"
