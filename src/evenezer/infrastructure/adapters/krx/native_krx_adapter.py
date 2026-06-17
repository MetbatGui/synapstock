import logging
import os
import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from evenezer.domain.ports import KrxDataPort, PriceDataPort

logger = logging.getLogger(__name__)


class NativeKrxAdapter(KrxDataPort, PriceDataPort):
    """KRX 내부 비공식 API를 직접 호출하여 데이터를 수집하는 어댑터. 
    세션 만료 자동 복구 및 재시도 메커니즘을 지원합니다.
    """

    BASE_URL = "https://data.krx.co.kr"

    def __init__(self):
        self.session = requests.Session()
        self.username = os.getenv("KRX_USERNAME")
        self.password = os.getenv("KRX_PASSWORD")
        self.is_logged_in = False

        self.otp_url = f"{self.BASE_URL}/comm/fileDn/GenerateOTP/generate.cmd"
        self.download_url = f"{self.BASE_URL}/comm/fileDn/download_excel/download.cmd"
        self.api_url = f"{self.BASE_URL}/comm/bldAttendant/getJsonData.cmd"

        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Referer": f"{self.BASE_URL}/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201",
            "X-Requested-With": "XMLHttpRequest",
        }
        self.session.headers.update(self.headers)

    def _login(self) -> bool:
        """KRX 정보데이터시스템 로그인 세션을 획득한다."""
        if not self.username or not self.password:
            logger.error("[KRX] 로그인 계정 정보(KRX_USERNAME/PASSWORD)가 설정되지 않았습니다.")
            return False

        login_url = f"{self.BASE_URL}/contents/MDC/COMS/client/MDCCOMS001D1.cmd"
        payload = {"mbrId": self.username, "pw": self.password}

        try:
            # 초기 페이지 접근으로 세션 초기화
            self.session.get(f"{self.BASE_URL}/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201")

            resp = self.session.post(login_url, data=payload)
            data = resp.json()

            if data.get("_error_code") == "CD011":  # 중복 로그인 처리
                payload["skipDup"] = "Y"
                resp = self.session.post(login_url, data=payload)
                data = resp.json()

            if data.get("_error_code") == "CD001":
                logger.info(f"[KRX] 로그인 성공: {self.username}")
                self.is_logged_in = True
                return True
            else:
                logger.error(f"[KRX] 로그인 실패: {data}")
                self.is_logged_in = False
                return False
        except Exception as e:
            logger.error(f"[KRX] 로그인 프로세스 중 오류 발생: {e}")
            self.is_logged_in = False
            return False

    @retry(
        wait=wait_exponential(multiplier=1, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(RuntimeError),
        reraise=True
    )
    def fetch_net_purchase_data(self, market: str, investor: str, date_str: str) -> bytes:
        """투자자별 순매수 전종목 엑셀 수집 (MDCSTAT02401)."""
        if not self.is_logged_in:
            if not self._login():
                raise RuntimeError("KRX 로그인에 실패하여 수집을 시작할 수 없습니다.")

        otp_params = {
            "locale": "ko_KR",
            "mktId": market,  # STK, KSQ
            "invstTpCd": investor,  # 7050(기관), 9000(외국인-사용자기준)
            "strtDd": date_str,
            "endDd": date_str,
            "share": "1",
            "money": "1",
            "csvxls_isNo": "false",
            "name": "fileDown",
            "url": "dbms/MDC/STAT/standard/MDCSTAT02401",
        }
        if market == "KSQ":
            otp_params["segTpCd"] = "ALL"

        try:
            otp_resp = self.session.post(self.otp_url, data=otp_params)
            otp_code = otp_resp.text.strip()

            if len(otp_code) < 10:
                logger.error(f"[KRX] OTP 발급 실패 ({market}-{investor}). 세션을 초기화합니다.")
                self.is_logged_in = False
                raise RuntimeError("OTP 발급 실패 (세션 만료 가능성)")

            down_resp = self.session.post(self.download_url, data={"code": otp_code})
            
            # 다운로드 응답이 로그인 유도 HTML인 경우 세션 만료 처리
            if b"html" in down_resp.content[:100].lower():
                logger.error("[KRX] 다운로드 응답이 엑셀이 아닌 HTML 형식입니다. 세션을 만료 처리합니다.")
                self.is_logged_in = False
                raise RuntimeError("엑셀 다운로드 응답이 올바르지 않음 (세션 만료)")
                
            return down_resp.content
        except Exception as e:
            if not isinstance(e, RuntimeError):
                logger.error(f"[KRX] 수급 데이터 수집 중 오류: {e}")
                raise RuntimeError(f"네트워크 오류로 수집 실패: {e}") from e
            raise e

    @retry(
        wait=wait_exponential(multiplier=1, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(RuntimeError),
        reraise=True
    )
    def fetch_investor_trading_data(self, market: str, date_str: str) -> bytes:
        """종목별 투자자 거래실적 수집 (MDCSTAT02201)."""
        if not self.is_logged_in:
            if not self._login():
                raise RuntimeError("KRX 로그인에 실패하여 수집을 시작할 수 없습니다.")

        otp_params = {
            "bld": "dbms/MDC/STAT/standard/MDCSTAT02201",
            "locale": "ko_KR",
            "inqTpCd": "1",  # 투자자별 합계
            "trdVolVal": "2",  # 거래대금 기반
            "askBid": "3",  # 순매수 기준
            "mktId": market,  # STK, KSQ
            "etf": "EF",
            "etn": "EN",
            "elw": "EW",
            "strtDd": date_str,
            "endDd": date_str,
            "share": "1",
            "money": "1",
            "csvxls_isNo": "false",
            "name": "fileDown",
            "url": "dbms/MDC/STAT/standard/MDCSTAT02201",
        }

        try:
            otp_resp = self.session.post(self.otp_url, data=otp_params)
            otp_code = otp_resp.text.strip()

            if len(otp_code) < 10:
                logger.error(f"[KRX] OTP 발급 실패 (MDCSTAT02201-{market}). 세션을 초기화합니다.")
                self.is_logged_in = False
                raise RuntimeError("OTP 발급 실패 (세션 만료 가능성)")

            down_resp = self.session.post(self.download_url, data={"code": otp_code})
            
            # 다운로드 응답이 로그인 유도 HTML인 경우 세션 만료 처리
            if b"html" in down_resp.content[:100].lower():
                logger.error("[KRX] 다운로드 응답이 엑셀이 아닌 HTML 형식입니다. 세션을 만료 처리합니다.")
                self.is_logged_in = False
                raise RuntimeError("엑셀 다운로드 응답이 올바르지 않음 (세션 만료)")
                
            return down_resp.content
        except Exception as e:
            if not isinstance(e, RuntimeError):
                logger.error(f"[KRX] 투자자 거래실적 수집 중 오류: {e}")
                raise RuntimeError(f"네트워크 오류로 수집 실패: {e}") from e
            raise e

    @retry(
        wait=wait_exponential(multiplier=1, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(RuntimeError),
        reraise=True
    )
    def fetch_market_prices(self, market: str, date_str: str) -> list[dict]:
        """전종목 등락률/시세 조회 (MDCSTAT01501)."""
        if not self.is_logged_in:
            if not self._login():
                raise RuntimeError("KRX 로그인에 실패하여 조회를 시작할 수 없습니다.")

        payload = {
            "bld": "dbms/MDC/STAT/standard/MDCSTAT01501",
            "locale": "ko_KR",
            "mktId": market,  # STK, KSQ
            "trdDd": date_str,
            "share": "1",
            "money": "1",
            "csvxls_isNo": "false",
        }
        try:
            resp = self.session.post(self.api_url, data=payload)
            
            # 응답이 비정상이거나 HTML 형식인 경우 세션 만료 의심
            if resp.status_code != 200 or b"html" in resp.content[:100].lower():
                logger.error("[KRX] 시세 API 응답이 올바르지 않습니다. 세션을 초기화합니다.")
                self.is_logged_in = False
                raise RuntimeError("시세 API 응답 이상 (세션 만료)")
                
            data = resp.json()
            return data.get("OutBlock_1", []) or data.get("output", [])
        except Exception as e:
            if not isinstance(e, RuntimeError):
                logger.error(f"[KRX] 전종목 시세 조회 중 오류: {e}")
                raise RuntimeError(f"네트워크 오류로 시세 조회 실패: {e}") from e
            raise e

    def get_price_info(self, ticker: str, date_str: str) -> dict | None:
        """특정 종목 일자별 시세 조회 (MDCSTAT01701)."""
        # ISO 종목 풀코드 조회를 위한 임시 맵 필요
        pass
