import pytest
from unittest.mock import MagicMock, patch
import pandas as pd
from datetime import datetime, timedelta
import requests

from synapstock.infrastructure.adapters.krx.native_krx_adapter import NativeKrxAdapter
from synapstock.infrastructure.adapters.heatmap.krx_repository import KrxRepository


class MockResponse:
    def __init__(self, json_data=None, text="", content=b"", status_code=200):
        self._json_data = json_data or {}
        self.text = text
        self.content = content
        self.status_code = status_code

    def json(self):
        return self._json_data


# -----------------------------------------------------------------------------
# NativeKrxAdapter Tests
# -----------------------------------------------------------------------------

def test_native_krx_adapter_init():
    """NativeKrxAdapter 초기화 시 기본 필드들과 헤더가 정상 설정되는지 테스트합니다."""
    with patch.dict("os.environ", {"KRX_USERNAME": "test_user", "KRX_PASSWORD": "test_password"}):
        adapter = NativeKrxAdapter()
        assert adapter.username == "test_user"
        assert adapter.password == "test_password"
        assert adapter.is_logged_in is False
        assert "User-Agent" in adapter.session.headers
        assert "Referer" in adapter.session.headers


def test_native_krx_adapter_login_no_env():
    """로그인 계정 정보 환경변수가 설정되지 않은 경우 로그인 실패 처리되는지 테스트합니다."""
    with patch.dict("os.environ", {}, clear=True):
        adapter = NativeKrxAdapter()
        # __init__ 호출 후에 환경 변수가 없으므로 username, password는 None일 것
        adapter.username = None
        adapter.password = None
        assert adapter._login() is False
        assert adapter.is_logged_in is False


def test_native_krx_adapter_login_success():
    """정상적인 로그인 흐름(CD001)을 테스트합니다."""
    adapter = NativeKrxAdapter()
    adapter.username = "user"
    adapter.password = "pass"

    # 진짜 session 객체에 대해 get/post 메서드만 모킹
    adapter.session.get = MagicMock(return_value=MockResponse(text="html"))
    adapter.session.post = MagicMock(return_value=MockResponse(json_data={"_error_code": "CD001"}))

    assert adapter._login() is True
    assert adapter.is_logged_in is True
    adapter.session.get.assert_called_once()
    adapter.session.post.assert_called_once()


def test_native_krx_adapter_login_duplicate():
    """중복 로그인(CD011) 발생 시 skipDup="Y"를 추가하여 재시도 및 로그인 성공을 검증합니다."""
    adapter = NativeKrxAdapter()
    adapter.username = "user"
    adapter.password = "pass"

    adapter.session.get = MagicMock(return_value=MockResponse(text="html"))
    adapter.session.post = MagicMock(side_effect=[
        MockResponse(json_data={"_error_code": "CD011"}),
        MockResponse(json_data={"_error_code": "CD001"})
    ])

    assert adapter._login() is True
    assert adapter.is_logged_in is True
    assert adapter.session.post.call_count == 2
    
    second_call_data = adapter.session.post.call_args_list[1][1]["data"]
    assert second_call_data["skipDup"] == "Y"


def test_native_krx_adapter_login_failure():
    """로그인 요청 결과가 CD001이 아닐 때 로그인 실패 처리되는지 검증합니다."""
    adapter = NativeKrxAdapter()
    adapter.username = "user"
    adapter.password = "pass"

    adapter.session.get = MagicMock(return_value=MockResponse(text="html"))
    adapter.session.post = MagicMock(return_value=MockResponse(json_data={"_error_code": "CD002"}))

    assert adapter._login() is False
    assert adapter.is_logged_in is False


def test_native_krx_adapter_login_exception():
    """로그인 진행 중 예외 발생 시 안전하게 False를 리턴하는지 테스트합니다."""
    adapter = NativeKrxAdapter()
    adapter.username = "user"
    adapter.password = "pass"

    adapter.session.get = MagicMock(side_effect=Exception("Network timeout"))

    assert adapter._login() is False
    assert adapter.is_logged_in is False


def test_fetch_net_purchase_data_success():
    """투자자 순매수 엑셀 데이터를 정상 수집하는지 검증합니다. (STK 및 KSQ 대응)"""
    adapter = NativeKrxAdapter()
    adapter.is_logged_in = True  # 이미 로그인된 상태 가정
    
    adapter.session.post = MagicMock(side_effect=[
        MockResponse(text="OTP_CODE_1234567890"),
        MockResponse(content=b"excel_bytes_data")
    ])

    # 1. STK 시장 테스트
    result = adapter.fetch_net_purchase_data(market="STK", investor="7050", date_str="20260610")
    assert result == b"excel_bytes_data"
    assert adapter.session.post.call_count == 2

    # 2. KSQ 시장 테스트 (segTpCd = "ALL" 파라미터가 포함되어야 함)
    adapter.session.post = MagicMock(side_effect=[
        MockResponse(text="OTP_CODE_1234567890"),
        MockResponse(content=b"excel_bytes_ksq")
    ])
    result_ksq = adapter.fetch_net_purchase_data(market="KSQ", investor="9000", date_str="20260610")
    assert result_ksq == b"excel_bytes_ksq"
    otp_data = adapter.session.post.call_args_list[0][1]["data"]
    assert otp_data["segTpCd"] == "ALL"


def test_fetch_net_purchase_data_not_logged_in():
    """로그인이 안 된 상태일 때 fetch_net_purchase_data 내에서 _login을 호출하는지 검증합니다."""
    adapter = NativeKrxAdapter()
    adapter.is_logged_in = False
    
    # _login을 모킹하여 True 반환
    with patch.object(adapter, "_login", return_value=True) as mock_login:
        adapter.session.post = MagicMock(side_effect=[
            MockResponse(text="OTP_CODE_1234567890"),
            MockResponse(content=b"excel_bytes_data")
        ])
        
        result = adapter.fetch_net_purchase_data(market="STK", investor="7050", date_str="20260610")
        assert result == b"excel_bytes_data"
        mock_login.assert_called_once()


def test_fetch_net_purchase_data_otp_fail():
    """OTP 발급 응답이 10자 미만일 때 빈 바이트(b"")를 반환하는지 검증합니다."""
    adapter = NativeKrxAdapter()
    adapter.is_logged_in = True
    
    adapter.session.post = MagicMock(return_value=MockResponse(text="FAIL"))

    result = adapter.fetch_net_purchase_data(market="STK", investor="7050", date_str="20260610")
    assert result == b""
    assert adapter.session.post.call_count == 1  # 다운로드 요청은 보내지 않음


def test_fetch_net_purchase_data_exception():
    """요청 중 예외 발생 시 안전하게 빈 바이트(b"")를 리턴하는지 검증합니다."""
    adapter = NativeKrxAdapter()
    adapter.is_logged_in = True
    
    adapter.session.post = MagicMock(side_effect=Exception("Connection error"))

    result = adapter.fetch_net_purchase_data(market="STK", investor="7050", date_str="20260610")
    assert result == b""


def test_fetch_investor_trading_data_success():
    """종목별 투자자 거래실적 수집이 정상 동작하는지 테스트합니다."""
    adapter = NativeKrxAdapter()
    adapter.is_logged_in = True
    
    adapter.session.post = MagicMock(side_effect=[
        MockResponse(text="OTP_CODE_1234567890"),
        MockResponse(content=b"investor_trading_excel")
    ])

    result = adapter.fetch_investor_trading_data(market="STK", date_str="20260610")
    assert result == b"investor_trading_excel"
    assert adapter.session.post.call_count == 2
    
    # 파라미터 체크
    otp_data = adapter.session.post.call_args_list[0][1]["data"]
    assert otp_data["bld"] == "dbms/MDC/STAT/standard/MDCSTAT02201"
    assert otp_data["trdVolVal"] == "2"


def test_fetch_investor_trading_data_not_logged_in():
    """로그인이 안 된 상태일 때 fetch_investor_trading_data 내에서 _login을 호출하는지 검증합니다."""
    adapter = NativeKrxAdapter()
    adapter.is_logged_in = False
    
    with patch.object(adapter, "_login", return_value=True) as mock_login:
        adapter.session.post = MagicMock(side_effect=[
            MockResponse(text="OTP_CODE_1234567890"),
            MockResponse(content=b"investor_trading_excel")
        ])
        
        result = adapter.fetch_investor_trading_data(market="STK", date_str="20260610")
        assert result == b"investor_trading_excel"
        mock_login.assert_called_once()


def test_fetch_investor_trading_data_otp_fail():
    """투자자 거래실적 OTP 발급 실패 시 시나리오를 테스트합니다."""
    adapter = NativeKrxAdapter()
    adapter.is_logged_in = True
    
    adapter.session.post = MagicMock(return_value=MockResponse(text="ERROR"))

    result = adapter.fetch_investor_trading_data(market="STK", date_str="20260610")
    assert result == b""


def test_fetch_investor_trading_data_exception():
    """투자자 거래실적 수집 도중 예외 발생 시 시나리오를 테스트합니다."""
    adapter = NativeKrxAdapter()
    adapter.is_logged_in = True
    
    adapter.session.post = MagicMock(side_effect=Exception("Timeout"))

    result = adapter.fetch_investor_trading_data(market="STK", date_str="20260610")
    assert result == b""


def test_fetch_market_prices_success_outblock():
    """전종목 시세 데이터 응답이 OutBlock_1으로 올 때 정상 변환되는지 테스트합니다."""
    adapter = NativeKrxAdapter()
    adapter.is_logged_in = True
    
    mock_data = [{"ISU_SRT_CD": "005930", "ISU_ABBRV": "삼성전자"}]
    adapter.session.post = MagicMock(return_value=MockResponse(json_data={"OutBlock_1": mock_data}))

    result = adapter.fetch_market_prices(market="STK", date_str="20260610")
    assert result == mock_data


def test_fetch_market_prices_success_output():
    """전종목 시세 데이터 응답이 output으로 올 때 정상 변환되는지 테스트합니다."""
    adapter = NativeKrxAdapter()
    adapter.is_logged_in = True
    
    mock_data = [{"ISU_SRT_CD": "000660", "ISU_ABBRV": "SK하이닉스"}]
    adapter.session.post = MagicMock(return_value=MockResponse(json_data={"output": mock_data}))

    result = adapter.fetch_market_prices(market="STK", date_str="20260610")
    assert result == mock_data


def test_fetch_market_prices_not_logged_in():
    """로그인이 안 된 상태일 때 fetch_market_prices 내에서 _login을 호출하는지 검증합니다."""
    adapter = NativeKrxAdapter()
    adapter.is_logged_in = False
    
    with patch.object(adapter, "_login", return_value=True) as mock_login:
        mock_data = [{"ISU_SRT_CD": "005930", "ISU_ABBRV": "삼성전자"}]
        adapter.session.post = MagicMock(return_value=MockResponse(json_data={"OutBlock_1": mock_data}))
        
        result = adapter.fetch_market_prices(market="STK", date_str="20260610")
        assert result == mock_data
        mock_login.assert_called_once()


def test_fetch_market_prices_exception():
    """전종목 시세 데이터 조회 중 예외 발생 시 빈 리스트를 반환하는지 테스트합니다."""
    adapter = NativeKrxAdapter()
    adapter.is_logged_in = True
    
    adapter.session.post = MagicMock(side_effect=Exception("JSON decode error"))

    result = adapter.fetch_market_prices(market="STK", date_str="20260610")
    assert result == []


def test_native_krx_adapter_get_price_info():
    """get_price_info 메서드가 정상 호출 및 pass 되는지 검증합니다."""
    adapter = NativeKrxAdapter()
    result = adapter.get_price_info("005930", "20260610")
    assert result is None


# -----------------------------------------------------------------------------
# KrxRepository Tests
# -----------------------------------------------------------------------------

def test_krx_repository_init():
    """KrxRepository 초기화 시 세션 설정 및 dotenv 환경변수 로드가 동작하는지 확인합니다."""
    with patch.dict("os.environ", {"KRX_USERNAME": "repo_user", "KRX_PASSWORD": "repo_password"}):
        repo = KrxRepository()
        assert repo.username == "repo_user"
        assert repo.password == "repo_password"
        assert repo.is_logged_in is False
        assert "User-Agent" in repo.session.headers
        assert repo.session.headers["X-Requested-With"] == "XMLHttpRequest"


def test_krx_repository_login_no_env():
    """계정 정보 환경변수가 없는 경우 로그인 생략 및 익명 세션으로 진행하는지 확인합니다."""
    repo = KrxRepository()
    repo.username = None
    repo.password = None
    
    repo.session.get = MagicMock()
    repo.session.post = MagicMock()
    
    repo._login()
    assert repo.is_logged_in is False
    repo.session.get.assert_not_called()
    repo.session.post.assert_not_called()


def test_krx_repository_login_success():
    """KrxRepository 로그인 성공 흐름을 검증합니다."""
    repo = KrxRepository()
    repo.username = "repo_user"
    repo.password = "repo_password"

    repo.session.get = MagicMock(return_value=MockResponse(text="html"))
    repo.session.post = MagicMock(return_value=MockResponse(json_data={"_error_code": "CD001", "MBR_NO": "12345"}))

    repo._login()
    assert repo.is_logged_in is True
    assert repo.session.get.call_count == 2
    assert repo.session.post.call_count == 1
    # 쿠키 셋팅 확인
    assert repo.session.cookies.get('mdc.client_session', domain='data.krx.co.kr') == 'true'
    assert repo.session.cookies.get('lang', domain='data.krx.co.kr') == 'ko_KR'


def test_krx_repository_login_duplicate():
    """KrxRepository 중복 로그인(CD011) 시 재요청을 통해 성공하는지 검증합니다."""
    repo = KrxRepository()
    repo.username = "repo_user"
    repo.password = "repo_password"

    repo.session.get = MagicMock(return_value=MockResponse(text="html"))
    repo.session.post = MagicMock(side_effect=[
        MockResponse(json_data={"_error_code": "CD011"}),
        MockResponse(json_data={"_error_code": "CD001", "MBR_NO": "12345"})
    ])

    repo._login()
    assert repo.is_logged_in is True
    assert repo.session.post.call_count == 2
    
    second_call_data = repo.session.post.call_args_list[1][1]["data"]
    assert second_call_data["skipDup"] == "Y"


def test_krx_repository_login_failure():
    """KrxRepository 로그인 에러 응답 반환 시 실패 처리를 검증합니다."""
    repo = KrxRepository()
    repo.username = "repo_user"
    repo.password = "repo_password"

    repo.session.get = MagicMock(return_value=MockResponse(text="html"))
    repo.session.post = MagicMock(return_value=MockResponse(json_data={"_error_code": "CD099"}))

    repo._login()
    assert repo.is_logged_in is False


def test_krx_repository_login_exception():
    """KrxRepository 로그인 요청 도중 예외가 발생하는 경우의 처리를 검증합니다."""
    repo = KrxRepository()
    repo.username = "repo_user"
    repo.password = "repo_password"

    repo.session.get = MagicMock(side_effect=Exception("Connection reset by peer"))

    repo._login()
    assert repo.is_logged_in is False


def test_krx_repository_fetch_listing_success():
    """전종목 데이터를 조회하여 Pandas DataFrame으로의 변환이 정상 수행되는지 검증합니다."""
    repo = KrxRepository()
    repo.is_logged_in = True

    mock_output = [
        {"ISU_SRT_CD": "005930", "ISU_ABBRV": "삼성전자", "MKTCAP": "350,000,000", "FLUC_RT": "1.5"},
        {"ISU_SRT_CD": "000660", "ISU_ABBRV": "SK하이닉스", "MKTCAP": "80,000,000", "FLUC_RT": "-0.5"},
    ]
    repo.session.post = MagicMock(return_value=MockResponse(json_data={"OutBlock_1": mock_output}))

    df = repo.fetch_listing(date=datetime(2026, 6, 10))
    
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    assert list(df.columns) == ["Code", "Name", "Marcap", "ChagesRatio"]
    
    # 첫번째 행 값 검증 (콤마가 제거되어 float로 변환되었는지 체크)
    assert df.loc[0, "Code"] == "005930"
    assert df.loc[0, "Name"] == "삼성전자"
    assert df.loc[0, "Marcap"] == 350000000.0
    assert df.loc[0, "ChagesRatio"] == 1.5


def test_krx_repository_fetch_listing_no_date():
    """date 매개변수가 생략되었을 때 기본 오늘 날짜를 기준으로 정상 호출되는지 검증합니다."""
    repo = KrxRepository()
    repo.is_logged_in = True

    repo.session.post = MagicMock(return_value=MockResponse(json_data={"OutBlock_1": []}))

    # 10일 루프 실패하여 빈 df 반환되겠지만 호출 날짜 파라미터는 오늘 기준일 것
    df = repo.fetch_listing(date=None)
    assert df.empty
    
    # 최초 호출된 데이터 파라미터의 trdDd 형태 검증 (%Y%m%d)
    first_call_data = repo.session.post.call_args_list[0][1]["data"]
    assert len(first_call_data["trdDd"]) == 8


def test_krx_repository_fetch_listing_auto_login():
    """로그인이 안 되어 있고 username/password가 있을 때 fetch_listing 내부에서 자동 로그인 동작을 검증합니다."""
    repo = KrxRepository()
    repo.username = "repo_user"
    repo.password = "repo_password"
    repo.is_logged_in = False

    repo.session.post = MagicMock(return_value=MockResponse(json_data={"OutBlock_1": []}))

    def set_logged_in():
        repo.is_logged_in = True

    with patch.object(repo, "_login", side_effect=set_logged_in) as mock_login:
        df = repo.fetch_listing(date=datetime(2026, 6, 10))
        assert df.empty
        mock_login.assert_called_once()


def test_krx_repository_fetch_listing_retry_on_non_business_day():
    """조회일이 영업일이 아닌 경우(데이터 없음), 최대 10일 이전까지 이전 날짜로 재시도하는 흐름을 검증합니다."""
    repo = KrxRepository()
    repo.is_logged_in = True

    # 처음 2번은 빈 데이터 반환 (주말 등), 3번째 시도에서 데이터 반환
    repo.session.post = MagicMock(side_effect=[
        MockResponse(json_data={"OutBlock_1": []}),
        MockResponse(json_data={"OutBlock_1": []}),
        MockResponse(json_data={"output": [
            {"ISU_SRT_CD": "005930", "ISU_ABBRV": "삼성전자", "MKTCAP": "350,000,000", "FLUC_RT": "1.5"}
        ]})
    ])

    df = repo.fetch_listing(date=datetime(2026, 6, 10))
    
    assert len(df) == 1
    assert df.loc[0, "Code"] == "005930"
    # 총 3번의 POST 호출이 이루어졌는지 확인
    assert repo.session.post.call_count == 3


def test_krx_repository_fetch_listing_10days_all_failure():
    """10일 영업일 탐색 재시도가 모두 실패할 경우 빈 DataFrame을 반환하는지 테스트합니다."""
    repo = KrxRepository()
    repo.is_logged_in = True

    repo.session.post = MagicMock(return_value=MockResponse(json_data={"OutBlock_1": []}))

    df = repo.fetch_listing(date=datetime(2026, 6, 10))
    
    assert df.empty
    # 정확히 10번 재시도 하였는지 검증
    assert repo.session.post.call_count == 10


def test_krx_repository_fetch_listing_session_expired_relogin():
    """응답 본문에 'LOGOUT' 감지 시 세션 만료로 판단하고 재로그인을 수행한 뒤 재시도하는지 테스트합니다."""
    repo = KrxRepository()
    repo.username = "repo_user"
    repo.password = "repo_password"
    repo.is_logged_in = True

    # 첫번째 시도에서 LOGOUT 반환 -> _login 호출됨 -> 두번째 시도에서 정상 데이터 반환
    repo.session.post = MagicMock(side_effect=[
        MockResponse(text="error LOGOUT required"),
        MockResponse(json_data={"OutBlock_1": [
            {"ISU_SRT_CD": "005930", "ISU_ABBRV": "삼성전자", "MKTCAP": "350,000,000", "FLUC_RT": "1.5"}
        ]})
    ])

    with patch.object(repo, "_login") as mock_login:
        df = repo.fetch_listing(date=datetime(2026, 6, 10))
        
        assert len(df) == 1
        assert df.loc[0, "Code"] == "005930"
        # LOGOUT 감지 후 재로그인 함수가 호출되었는지 확인
        mock_login.assert_called_once()
        # post가 총 2번 호출됨 (만료 시 1회, 재로그인 후 재전송 1회)
        assert repo.session.post.call_count == 2


def test_krx_repository_fetch_listing_exception_loop():
    """특정 영업일 데이터 수집 중 예외 발생 시 다음 날짜로 재시도를 계속 진행하는지 검증합니다."""
    repo = KrxRepository()
    repo.is_logged_in = True

    # 첫번째는 예외 발생, 두번째는 정상 데이터 반환
    repo.session.post = MagicMock(side_effect=[
        Exception("Connection reset"),
        MockResponse(json_data={"OutBlock_1": [
            {"ISU_SRT_CD": "005930", "ISU_ABBRV": "삼성전자", "MKTCAP": "350,000,000", "FLUC_RT": "1.5"}
        ]})
    ])

    df = repo.fetch_listing(date=datetime(2026, 6, 10))
    
    assert len(df) == 1
    assert df.loc[0, "Code"] == "005930"
    assert repo.session.post.call_count == 2


def test_krx_repository_fetch_listing_last_attempt_exception():
    """10번째(마지막) 루프에서 예외 발생 시 바로 빈 DataFrame을 반환하고 중지하는지 검증합니다."""
    repo = KrxRepository()
    repo.is_logged_in = True

    # 9번은 빈 데이터 반환, 마지막 10번째는 예외 발생
    side_effects = [MockResponse(json_data={"OutBlock_1": []})] * 9 + [Exception("Last attempt failed")]
    repo.session.post = MagicMock(side_effect=side_effects)

    df = repo.fetch_listing(date=datetime(2026, 6, 10))
    
    assert df.empty
    assert repo.session.post.call_count == 10
