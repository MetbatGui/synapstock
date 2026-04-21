from enum import StrEnum

from pydantic import BaseModel, computed_field


class MarketType(StrEnum):
    """주식 시장 유형.

    Attributes:
        KOSPI: 유가증권시장.
        KOSDAQ: 코스닥시장.
    """
    KOSPI = "KOSPI"
    KOSDAQ = "KOSDAQ"

class SupplySubject(StrEnum):
    """수급 주체 유형.

    Attributes:
        FOREIGN: 외국인 투자자.
        INSTITUTION: 기관 투자자.
    """
    FOREIGN = "FOREIGN"
    INSTITUTION = "INSTITUTION"

class RankingItem(BaseModel):
    """수급 순위표의 개별 종목 항목 모델.

    Attributes:
        rank (int): 해당 종목의 순위.
        name (str): 종목명.
        amount (int): 순매수 금액 (단위: 억 또는 천만, 엑셀 기준).
        ticker (Optional[str]): 시스템 내 매칭된 전문 티커 번호.
        high_price_type (Optional[str]): 신고가 유형 약어 (예: 역·신, 52·근).
    """
    rank: int
    name: str
    amount: int
    ticker: str | None = None
    high_price_type: str | None = None

class DailyMarketRanking(BaseModel):
    """특정 마켓 및 주체의 일별 수급 TOP 30 리포트 모델.

    Attributes:
        date (str): 기준 날짜 (YYYY-MM-DD).
        market (MarketType): 시장 유형.
        subject (SupplySubject): 수급 주체.
        items (List[RankingItem]): 순위 항목 리스트.
    """
    date: str
    market: MarketType
    subject: SupplySubject
    items: list[RankingItem]

class MonthlyMarketStats(BaseModel):
    """월간 누적 수급 통계 모델.

    Attributes:
        month (str): 기준 월 (YYYY-MM).
        market (MarketType): 시장 유형.
        subject (SupplySubject): 수급 주체.
        items (List[RankingItem]): 누적 순위 항목 리스트 (최대 100개).
    """
    month: str
    market: MarketType
    subject: SupplySubject
    items: list[RankingItem]

# --- Analysis DTOs ---

class AnalyzedRankingItem(RankingItem):
    """순위 변동성 분석 정보가 포함된 확장 종목 모델.

    Attributes:
        prev_rank (Optional[int]): 이전 거래일의 순위.
        consecutive_days (int): 연속 상위권 등장 횟수 (기본값 1).
    """
    prev_rank: int | None = None
    consecutive_days: int = 1

    @computed_field
    def rank_change(self) -> int | None:
        """순위 변동폭 (이전 순위 - 현재 순위).

        Returns:
            Optional[int]: 변동폭. 이전 순위가 없으면 None.
        """
        if self.prev_rank is None:
            return None
        return self.prev_rank - self.rank

    @computed_field
    def is_new(self) -> bool:
        """신규 진입 여부 판단.

        Returns:
            bool: 이전 순위 정보가 없으면 True.
        """
        return self.prev_rank is None

class DailyMarketRankingAnalysis(BaseModel):
    """분석 정보가 포함된 종합 수급 분석 모델.

    Attributes:
        date (str): 기준 날짜.
        market (MarketType): 시장 유형.
        subject (SupplySubject): 수급 주체.
        items (List[AnalyzedRankingItem]): 분석 지표가 포함된 항목 리스트.
        previous_date (Optional[str]): 비교 대상이 된 이전 거래일 날짜.
    """
    date: str
    market: MarketType
    subject: SupplySubject
    items: list[AnalyzedRankingItem]
    previous_date: str | None = None

# --- Ceiling Analysis Models ---

class CeilingItem(BaseModel):
    """상한가 분석의 개별 종목 항목 모델.

    Attributes:
        name (str): 종목명.
        entry_tag (str): 진입 시점의 시장 상태 태그 (예: 상, 역·신).
        closing_prices (List[int]): n거래일 동안 수집된 종가 리스트.
        ticker (Optional[str]): 매칭된 티커 번호.
    """
    name: str
    entry_tag: str
    closing_prices: list[int]
    ticker: str | None = None

    @computed_field
    def change_rate(self) -> float:
        """기준일 대비 최종 수익률 (%) 계산.

        공식: ((현재가 - 진입가) / 진입가) * 100

        Returns:
            float: 소수점 둘째 자리까지 반올림된 수익률.
        """
        if not self.closing_prices or len(self.closing_prices) < 2:
            return 0.0
        first = self.closing_prices[0]
        last = self.closing_prices[-1]
        if first == 0:
            return 0.0
        return round(((last - first) / first) * 100, 2)

    @computed_field
    def is_completed(self) -> bool:
        """10거래일 데이터 수집 완료 여부 판단.

        Returns:
            bool: 가격 리스트 크기가 10 이상이면 True.
        """
        return len(self.closing_prices) >= 10

class CeilingAnalysisReport(BaseModel):
    """상한가 분석 전체 리포트 모델.

    Attributes:
        title (str): 리포트 제목.
        start_date (str): 분석 시작일 (YYYY-MM-DD).
        end_date (str): 분석 종료일 (YYYY-MM-DD).
        dates (List[str]): 데이터가 존재하는 MM-DD 형식 날짜 목록.
        items (List[CeilingItem]): 분석 대상 종목 리스트.
    """
    title: str
    start_date: str
    end_date: str
    dates: list[str] = []
    items: list[CeilingItem]

    @computed_field
    def is_fully_collected(self) -> bool:
        """리포트 내 모든 종속 항목의 수집 완결 여부 확인.

        Returns:
            bool: 모든 item의 is_completed가 True인 경우 True.
        """
        return all(it.is_completed for it in self.items) if self.items else False


class PaidInCapitalIncrease(BaseModel):
    """유상증자 결정 공시 데이터 도메인 모델.

    사용자가 관리하는 엑셀 통계 구조(23개 칼럼)를 반영합니다.
    """
    date: str  # 일자 (YYYY-MM-DD)
    name: str  # 종목명
    is_correction: bool = False  # 기재정정여부
    disclosure_date: str  # 유상증자공시일
    rcp_no: str  # 접수번호
    parent_rcp_no: str | None = None  # 상위접수번호
    new_shares: int = 0  # 신주발행주식수
    face_value: int = 0  # 1주당 액면가
    pre_issued_shares: int = 0  # 증자전 발행주식총수
    fund_facility: int = 0  # 시설자금
    fund_operation: int = 0  # 운영자금
    fund_acquisition: int = 0  # 타법인증권
    fund_etc: int = 0  # 기타자금
    method: str = ""  # 증자방식 (제3자배정, 주주배정 등)
    issue_price: int = 0  # 신주의 발행가액
    confirmed_price: int | None = None  # 발행확정가액
    record_date: str | None = None  # 신주배정기준일
    shares_per_old: float | None = None  # 1주당 신주배정주식수
    subscription_date: str | None = None  # 청약예정일
    payment_date: str | None = None  # 납입일
    listing_date: str | None = None  # 신주상장일
    board_resolution_date: str | None = None  # 이사회결의일
    initial_disclosure_date: str | None = None  # 최초공시일
    ticker: str | None = None  # 시스템 연결용 티커

    @computed_field
    def total_fund(self) -> int:
        """총 자금조달 규모 합계.
        (시설 + 운영 + 타법인 + 기타)
        """
        return self.fund_facility + self.fund_operation + self.fund_acquisition + self.fund_etc


class BonusIssue(BaseModel):
    """무상증자 결정 공시 데이터 도메인 모델."""
    date: str  # 일자 (YYYY-MM-DD)
    name: str  # 종목명
    is_correction: bool = False  # 기재정정여부
    disclosure_date: str  # 무상증자공시일 (또는 일자)
    rcp_no: str  # 접수번호
    parent_rcp_no: str | None = None  # 상위접수번호
    new_shares: int = 0  # 신주발행주식수 (신주의 종류와 수)
    face_value: int = 0  # 1주당 액면가 (1주당 액면가액)
    pre_issued_shares: int = 0  # 증자전 발행주식총수
    shares_per_old: float = 0.0  # 1주당 신주배정주식수
    record_date: str | None = None  # 신주배정기준일
    listing_date: str | None = None  # 신주상장일 (신주의 상장 예정일)
    capital_reserve: str = ""  # 무상증자 재원 (주식발행초과금 등)
    board_resolution_date: str | None = None  # 이사회결의일
    initial_disclosure_date: str | None = None  # 최초공시일
    ticker: str | None = None  # 시스템 연결용 티커
