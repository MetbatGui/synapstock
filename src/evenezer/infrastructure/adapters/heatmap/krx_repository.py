import os
import requests
import pandas as pd
import logging
from datetime import datetime, timedelta
from typing import Optional
from evenezer.domain.heatmap.ports import KrxDataPort

logger = logging.getLogger(__name__)

class KrxRepository(KrxDataPort):
    """KRX API 직접 호출 기반 데이터 저장소 (외부 의존성 없음)"""
    
    BASE_URL = "https://data.krx.co.kr"
    
    def __init__(self):
        self.session = requests.Session()
        self.user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
        self.session.headers.update({
            'User-Agent': self.user_agent,
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Origin': self.BASE_URL,
            'Referer': f'{self.BASE_URL}/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201',
            'X-Requested-With': 'XMLHttpRequest'
        })
        
        from dotenv import load_dotenv
        load_dotenv()
        
        self.username = os.getenv("KRX_USERNAME")
        self.password = os.getenv("KRX_PASSWORD")
        self.is_logged_in = False

    def _login(self) -> None:
        """KRX 정보데이터시스템 로그인 세션 쿠키 갱신"""
        if not self.username or not self.password:
            logger.debug("KRX_USERNAME 또는 KRX_PASSWORD 환경변수가 설정되지 않아 익명(Anonymous) 세션으로 진행합니다.")
            return

        _LOGIN_PAGE = f"{self.BASE_URL}/contents/MDC/COMS/client/MDCCOMS001.cmd"
        _LOGIN_JSP  = f"{self.BASE_URL}/contents/MDC/COMS/client/view/login.jsp?site=mdc"
        _LOGIN_URL  = f"{self.BASE_URL}/contents/MDC/COMS/client/MDCCOMS001D1.cmd"
        
        try:
            self.session.get(_LOGIN_PAGE, timeout=15)
            self.session.get(_LOGIN_JSP, headers={"Referer": _LOGIN_PAGE}, timeout=15)
            
            payload = {
                "mbrNm": "", "telNo": "", "di": "", "certType": "",
                "mbrId": self.username, "pw": self.password,
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
                
            self.session.cookies.set('mdc.client_session', 'true', domain='data.krx.co.kr')
            self.session.cookies.set('lang', 'ko_KR', domain='data.krx.co.kr')
        except Exception as e:
            logger.error(f"KRX 로그인 요청 중 에러: {e}")
            self.is_logged_in = False

    def fetch_listing(self, date: Optional[datetime] = None) -> pd.DataFrame:
        """직접 KRX JSON API(MDCSTAT01501)를 호출하여 전종목 데이터를 수집합니다.
        
        Args:
            date: 조회할 기준일. None이면 오늘 날짜를 기준으로 조회합니다.
        
        Returns:
            KRX 종목 데이터프레임 (Code, Name, Marcap, ChagesRatio 컬럼 포함)
        """
        target_base = date or datetime.now()
        
        for i in range(10):
            attempt_date = target_base - timedelta(days=i)
            target_date_str = attempt_date.strftime('%Y%m%d')
            display_date = attempt_date.strftime('%Y-%m-%d')
            
            logger.info(f"KRX API 직접 호출 시도 중... (기준일: {display_date})")
            
            if not self.is_logged_in and self.username and self.password:
                self._login()
                
            url = f"{self.BASE_URL}/comm/bldAttendant/getJsonData.cmd"
            payload = {
                'bld': 'dbms/MDC/STAT/standard/MDCSTAT01501',
                'locale': 'ko_KR',
                'mktId': 'ALL',
                'trdDd': target_date_str,
                'share': '1',
                'money': '1',
                'csvxls_isNo': 'false',
            }
            
            try:
                res = self.session.post(url, data=payload, timeout=60)
                if 'LOGOUT' in res.text:
                    logger.debug("세션 만료 감지, 재로그인 수행 중...")
                    self._login()
                    res = self.session.post(url, data=payload, timeout=60)
                
                data = res.json()
                output = data.get('OutBlock_1', []) or data.get('output', [])
                
                if not output:
                    logger.debug(f"{display_date}은(는) 영업일이 아니거나 데이터가 존재하지 않습니다. 이전 날짜로 재시도합니다.")
                    if i == 9:
                        logger.error("최근 10일 이내의 영업일 데이터를 찾을 수 없습니다.")
                    continue
                
                rows = []
                for row in output:
                    code = row.get('ISU_SRT_CD')
                    name = row.get('ISU_ABBRV')
                    marcap_str = row.get('MKTCAP', '0').replace(',', '')
                    change_ratio_str = row.get('FLUC_RT', '0').replace(',', '')
                    
                    rows.append({
                        'Code': code,
                        'Name': name,
                        'Marcap': float(marcap_str) if marcap_str else 0.0,
                        'ChagesRatio': float(change_ratio_str) if change_ratio_str else 0.0
                    })
                    
                df_result = pd.DataFrame(rows)
                logger.info(f"네이티브 KRX API 호출 완료 (정상 영업일: {display_date}, 수집 종목 수: {len(df_result)})")
                return df_result
                
            except Exception as e:
                logger.error(f"{display_date} 기준 데이터 수집 중 오류: {e}")
                continue
                
        return pd.DataFrame()
