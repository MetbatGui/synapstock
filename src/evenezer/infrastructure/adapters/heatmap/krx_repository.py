import logging
import os
import time
from datetime import datetime, timedelta

import pandas as pd
import requests

from evenezer.domain.ports import KrxDataPort

logger = logging.getLogger(__name__)


class KrxRepository(KrxDataPort):
    """KRX 정보데이터시스템 JSON API 직접 호출 기반의 주식 정보 수집 리포지토리입니다."""

    BASE_URL = "https://data.krx.co.kr"

    def __init__(self):
        """KrxRepository를 초기화하고 HTTP 세션 헤더 및 환경 변수 기반 로그인 자격 증명을 로드합니다."""
        self.session = requests.Session()
        self.user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
        self.session.headers.update(
            {
                "User-Agent": self.user_agent,
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": self.BASE_URL,
                "Referer": f"{self.BASE_URL}/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201",
                "X-Requested-With": "XMLHttpRequest",
            }
        )

        from dotenv import load_dotenv

        load_dotenv()

        self.username = os.getenv("KRX_USERNAME")
        self.password = os.getenv("KRX_PASSWORD")
        self.is_logged_in = False

    def _login(self) -> None:
        """KRX 정보데이터시스템 회원 정보로 로그인 세션을 갱신하여 쿠키를 설정합니다.

        자격 증명 정보가 없으면 익명 사용자로 계속 진행합니다.
        """
        if not self.username or not self.password:
            logger.debug("KRX_USERNAME 또는 KRX_PASSWORD 환경변수가 설정되지 않아 익명(Anonymous) 세션으로 진행합니다.")
            return

        _LOGIN_PAGE = f"{self.BASE_URL}/contents/MDC/COMS/client/MDCCOMS001.cmd"
        _LOGIN_JSP = f"{self.BASE_URL}/contents/MDC/COMS/client/view/login.jsp?site=mdc"
        _LOGIN_URL = f"{self.BASE_URL}/contents/MDC/COMS/client/MDCCOMS001D1.cmd"

        try:
            self.session.get(_LOGIN_PAGE, timeout=15)
            self.session.get(_LOGIN_JSP, headers={"Referer": _LOGIN_PAGE}, timeout=15)

            payload = {
                "mbrNm": "",
                "telNo": "",
                "di": "",
                "certType": "",
                "mbrId": self.username,
                "pw": self.password,
            }
            headers = {"Referer": _LOGIN_PAGE}

            resp = self.session.post(_LOGIN_URL, data=payload, headers=headers, timeout=15)
            data = resp.json()
            error_code = data.get("_error_code", "")

            if error_code == "CD011":
                payload["skipDup"] = "Y"
                resp = self.session.post(_LOGIN_URL, data=payload, headers=headers, timeout=15)
                data = resp.json()
                error_code = data.get("_error_code", "")

            if error_code == "CD001":
                logger.info(f"KRX 세션 로그인 완료 (회원번호: {data.get('MBR_NO', '')})")
                self.is_logged_in = True
            else:
                logger.error(f"KRX 로그인 실패: {data}")
                self.is_logged_in = False

            self.session.cookies.set("mdc.client_session", "true", domain="data.krx.co.kr")
            self.session.cookies.set("lang", "ko_KR", domain="data.krx.co.kr")
        except Exception as e:
            logger.error(f"KRX 로그인 요청 중 에러: {e}")
            self.is_logged_in = False

    def fetch_listing(self, date: datetime | None = None) -> list[dict]:
        """직접 KRX JSON API(MDCSTAT01501)를 호출하여 특정 기준일의 전종목 데이터를 수집하고 list[dict]로 반환합니다.

        지정된 날짜가 영업일이 아닐 경우, 최대 10일 전까지 역순으로 탐색하며 영업일 데이터를 수집합니다.

        Args:
            date: 조회할 기준일. None일 경우 오늘 날짜를 기준으로 수집을 시작합니다.

        Returns:
            list[dict]: Code, Name, Marcap, ChagesRatio, Close 키가 포함된 딕셔너리 리스트.
        """
        target_base = date or datetime.now()
        df_result = self._fetch_listing_from_krx(target_base)
        if df_result.empty:
            return []
        return df_result.to_dict(orient="records")

    def _fetch_listing_from_krx(self, target_base: datetime) -> pd.DataFrame:
        """실제 KRX API를 호출하여 시세 데이터를 탐색 및 수집합니다."""
        for i in range(10):
            attempt_date = target_base - timedelta(days=i)
            target_date_str = attempt_date.strftime("%Y%m%d")
            display_date = attempt_date.strftime("%Y-%m-%d")

            logger.info(f"KRX API 직접 호출 시도 중... (기준일: {display_date})")

            if not self.is_logged_in and self.username and self.password:
                self._login()

            url = f"{self.BASE_URL}/comm/bldAttendant/getJsonData.cmd"
            payload = {
                "bld": "dbms/MDC/STAT/standard/MDCSTAT01501",
                "locale": "ko_KR",
                "mktId": "ALL",
                "trdDd": target_date_str,
                "share": "1",
                "money": "1",
                "csvxls_isNo": "false",
            }

            try:
                res = self.session.post(url, data=payload, timeout=60)
                if "LOGOUT" in res.text:
                    logger.debug("세션 만료 감지, 재로그인 수행 중...")
                    self._login()
                    res = self.session.post(url, data=payload, timeout=60)

                data = res.json()
                output = data.get("OutBlock_1", []) or data.get("output", [])

                if not output:
                    logger.debug(f"{display_date}은(는) 영업일이 아니거나 데이터가 없습니다. 이전 날짜 재시도.")
                    if i == 9:
                        logger.error("최근 10일 이내의 영업일 데이터를 찾을 수 없습니다.")
                    time.sleep(0.5)
                    continue

                rows = []
                for row in output:
                    code = row.get("ISU_SRT_CD")
                    name = row.get("ISU_ABBRV")
                    marcap_str = row.get("MKTCAP", "0").replace(",", "")
                    change_ratio_str = row.get("FLUC_RT", "0").replace(",", "")
                    close_price_str = row.get("TDD_CLSPRC", "0").replace(",", "")

                    rows.append(
                        {
                            "Code": code,
                            "Name": name,
                            "Marcap": float(marcap_str) if marcap_str else 0.0,
                            "ChagesRatio": float(change_ratio_str) if change_ratio_str else 0.0,
                            "Close": int(close_price_str) if close_price_str else 0,
                        }
                    )

                df_result = pd.DataFrame(rows)
                logger.info(f"네이티브 KRX API 호출 완료 (정상 영업일: {display_date}, 수집 종목 수: {len(df_result)})")
                return df_result

            except Exception as e:
                logger.error(f"{display_date} 기준 데이터 수집 중 오류: {e}")
                time.sleep(0.5)
                continue

        return pd.DataFrame()

    def fetch_net_purchase_data(self, market: str, investor: str, date_str: str) -> bytes:
        raise NotImplementedError("KrxRepository does not support fetch_net_purchase_data")

    def fetch_market_prices(self, market: str, date_str: str) -> list[dict]:
        raise NotImplementedError("KrxRepository does not support fetch_market_prices")
