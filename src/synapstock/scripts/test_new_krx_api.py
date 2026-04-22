import io
import os

import pandas as pd
import requests
from dotenv import load_dotenv


def test_investor_trading_api():
    load_dotenv()
    session = requests.Session()
    base_url = "https://data.krx.co.kr"

    # 1. 로그인 (필요한 경우)
    login_url = f"{base_url}/contents/MDC/COMS/client/MDCCOMS001D1.cmd"
    username = os.getenv("KRX_USERNAME")
    password = os.getenv("KRX_PASSWORD")

    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": f"{base_url}/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201",
        }
    )

    print("Loggin in...")
    session.get(f"{base_url}/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201")
    resp = session.post(login_url, data={"mbrId": username, "pw": password})
    if resp.json().get("_error_code") == "CD011":
        session.post(login_url, data={"mbrId": username, "pw": password, "skipDup": "Y"})

    # 2. OTP 발급 (MDCSTAT02201)
    # 사용자가 준 파라미터 기반
    payload = {
        "bld": "dbms/MDC/STAT/standard/MDCSTAT02201",
        "locale": "ko_KR",
        "inqTpCd": "1",  # 종목별
        "trdVolVal": "2",  # 거래대금
        "askBid": "3",  # 순매수
        "mktId": "STK",  # KOSPI
        "etf": "EF",
        "etn": "EN",
        "elw": "EW",
        "strtDd": "20260415",
        "endDd": "20260415",
        "share": "1",
        "money": "1",
        "csvxls_isNo": "false",
        "name": "fileDown",
        "url": "dbms/MDC/STAT/standard/MDCSTAT02201",
    }

    print("Generating OTP for MDCSTAT02201...")
    otp_url = f"{base_url}/comm/fileDn/GenerateOTP/generate.cmd"
    otp_resp = session.post(otp_url, data=payload)
    otp_code = otp_resp.text.strip()
    print(f"OTP: {otp_code}")

    # 3. 다운로드
    print("Downloading Excel...")
    down_url = f"{base_url}/comm/fileDn/download_excel/download.cmd"
    down_resp = session.post(down_url, data={"code": otp_code})

    # 4. 분석
    df = pd.read_excel(io.BytesIO(down_resp.content))
    print("\n=== Data Inspection (Indices and Values) ===")
    print(f"Total Rows: {len(df)}")
    print(f"Columns: {df.columns.tolist()}")

    for i, row in df.head(10).iterrows():
        print(f"\nRow {i}:")
        for j, val in enumerate(row):
            print(f"  Col {j}: {val}")

    # 투자자 구분과 수치 매핑 추정
    print("\n=== Investigation for MDCSTAT02201 ===")
    print("Assuming Col 0 is Category and Col 6 is Net Buy Value...")
    for i, row in df.iterrows():
        print(f"Category [{row.iloc[0]}]: Val at Col 6 = {row.iloc[6]}")

    # KSQ도 확인
    payload["mktId"] = "KSQ"
    otp_resp = session.post(otp_url, data=payload)
    down_resp = session.post(down_url, data={"code": otp_resp.text.strip()})
    df_ksq = pd.read_excel(io.BytesIO(down_resp.content))
    print("\n=== KOSDAQ Columns ===")
    print(df_ksq.columns.tolist())


if __name__ == "__main__":
    test_investor_trading_api()
