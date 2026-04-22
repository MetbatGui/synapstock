from enum import StrEnum

from pydantic import BaseModel, computed_field


class MarketType(StrEnum):
    """주식 시장 유형을 정의하는 열거형 클래스.

    Attributes:
        KOSPI: 유가증권 시장.
        KOSDAQ: 코스닥 시장.
    """

    KOSPI = "KOSPI"
    KOSDAQ = "KOSDAQ"


class SupplySubject(StrEnum):
    """수급 주체 유형을 정의하는 열거형 클래스.

    Attributes:
        FOREIGN: 외국인 투자자.
        INSTITUTION: 기관 투자자.
    """

    FOREIGN = "FOREIGN"
    INSTITUTION = "INSTITUTION"


class RankingItem(BaseModel):
    """수급 순위표의 개별 종목 항목 모델.

    Attributes:
        rank (int): 순위.
        name (str): 종목명.
        amount (int): 순매수 금액.
        ticker (str | None): 종목 코드 (선택 사항).
        high_price_type (str | None): 고가 유형 (선택 사항).
    """

    rank: int
    name: str
    amount: int
    ticker: str | None = None
    high_price_type: str | None = None


class DailyMarketRanking(BaseModel):
    """특정 마켓 및 주체의 일별 수급 TOP 30 리포트 모델.

    Attributes:
        date (str): 기준 일자 (YYYY-MM-DD).
        market (MarketType): 시장 유형 (KOSPI/KOSDAQ).
        subject (SupplySubject): 수급 주체 (FOREIGN/INSTITUTION).
        items (list[RankingItem]): 순위표 항목 리스트.
    """

    date: str
    market: MarketType
    subject: SupplySubject
    items: list[RankingItem]


class MonthlyMarketStats(BaseModel):
    """월간 누적 수급 통계 모델.

    Attributes:
        month (str): 기준 월 (YYYY-MM).
        market (MarketType): 시장 유형 (KOSPI/KOSDAQ).
        subject (SupplySubject): 수급 주체 (FOREIGN/INSTITUTION).
        items (list[RankingItem]): 누적 순위표 항목 리스트.
    """

    month: str
    market: MarketType
    subject: SupplySubject
    items: list[RankingItem]


class AnalyzedRankingItem(RankingItem):
    """순위 변동성 분석 정보가 포함된 확장 종목 모델.

    Attributes:
        prev_rank (int | None): 이전 거래일 순위.
        consecutive_days (int): 연속 순위권 진입 일수.
    """

    prev_rank: int | None = None
    consecutive_days: int = 1

    @computed_field
    def rank_change(self) -> int | None:
        """이전 순위 대비 변동 폭을 계산합니다.

        Returns:
            int | None: 순위 변동값 (상승 시 양수, 하락 시 음수). 이전 순위가 없으면 None.
        """
        if self.prev_rank is None:
            return None
        return self.prev_rank - self.rank

    @computed_field
    def is_new(self) -> bool:
        """순위권에 신규로 진입했는지 여부를 확인합니다.

        Returns:
            bool: 신규 진입 시 True, 아니면 False.
        """
        return self.prev_rank is None


class DailyMarketRankingAnalysis(BaseModel):
    """분석 정보가 포함된 종합 수급 분석 모델.

    Attributes:
        date (str): 기준 일자 (YYYY-MM-DD).
        market (MarketType): 시장 유형.
        subject (SupplySubject): 수급 주체.
        items (list[AnalyzedRankingItem]): 분석된 순위 항목 리스트.
        previous_date (str | None): 비교 대상 이전 일자.
    """

    date: str
    market: MarketType
    subject: SupplySubject
    items: list[AnalyzedRankingItem]
    previous_date: str | None = None


class CeilingItem(BaseModel):
    """상한가 분석의 개별 종목 항목 모델.

    Attributes:
        name (str): 종목명.
        entry_tag (str): 진입 태그/이유.
        closing_prices (list[int]): 최근 종가 리스트.
        ticker (str | None): 종목 코드.
    """

    name: str
    entry_tag: str
    closing_prices: list[int]
    ticker: str | None = None

    @computed_field
    def change_rate(self) -> float:
        """첫 번째 종가 대비 마지막 종가의 등락률을 계산합니다.

        Returns:
            float: 등락률 (백분율, 소수점 2자리 반올림).
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
        """충분한 데이터(10일치 이상)가 수집되었는지 확인합니다.

        Returns:
            bool: 데이터 수집 완료 여부.
        """
        return len(self.closing_prices) >= 10


class CeilingAnalysisReport(BaseModel):
    """상한가 분석 전체 리포트 모델."""

    title: str
    start_date: str
    end_date: str
    dates: list[str] = []
    items: list[CeilingItem]

    @computed_field
    def is_fully_collected(self) -> bool:
        return all(it.is_completed for it in self.items) if self.items else False


class BaseDisclosure(BaseModel):
    """공시 데이터의 공통 필드를 담는 기본 모델.

    Attributes:
        date (str): 공시 관련 기준 일자 (YYYY-MM-DD).
        name (str): 종목명.
        is_correction (bool): 기재정정 공시 여부.
        rcp_no (str): DART 접수번호.
        parent_rcp_no (str | None): 원본 공시 접수번호 (정정 공시인 경우).
        initial_disclosure_date (str | None): 최초 공시 일자.
        ticker (str | None): 종목 코드.
    """

    date: str
    name: str
    is_correction: bool = False
    rcp_no: str
    parent_rcp_no: str | None = None
    initial_disclosure_date: str | None = None
    ticker: str | None = None


class FundingDisclosure(BaseDisclosure):
    """자금 조달 관련 공시의 공통 필드를 담는 모델.

    Attributes:
        fund_facility (int): 시설자금.
        fund_operation (int): 운영자금.
        fund_acquisition_biz (int): 영업양수자금.
        fund_acquisition_sec (int): 타법인 증권 취득자금.
        fund_debt_repayment (int): 채무상환자금.
        fund_etc (int): 기타자금.
    """

    fund_facility: int = 0
    fund_operation: int = 0
    fund_acquisition_biz: int = 0
    fund_acquisition_sec: int = 0
    fund_debt_repayment: int = 0
    fund_etc: int = 0

    @computed_field
    def total_fund(self) -> int:
        """조달하려는 자금의 총합을 계산합니다.

        Returns:
            int: 전체 자금 합계.
        """
        return (
            self.fund_facility
            + self.fund_operation
            + self.fund_acquisition_biz
            + self.fund_acquisition_sec
            + self.fund_debt_repayment
            + self.fund_etc
        )


class PaidInCapitalIncrease(FundingDisclosure):
    """유상증자 결정 공시 데이터 도메인 모델.

    Attributes:
        disclosure_date (str): 실제 공시일.
        new_shares (int): 발행할 신주의 수.
        face_value (int): 1주당 액면가.
        pre_issued_shares (int): 증자 전 발행주식 총수.
        method (str): 증자 방식 (제3자배정 등).
        issue_price (int): 신주 발행 가액.
        confirmed_price (int | None): 확정 발행 가액.
        record_date (str | None): 신주배정 기준일.
        shares_per_old (float | None): 1주당 신주배정 주식수.
        subscription_date (str | None): 청약 예정일.
        payment_date (str | None): 납입일.
        listing_date (str | None): 신주 상장 예정일.
        board_resolution_date (str | None): 이사회 결의일.
    """

    disclosure_date: str
    new_shares: int = 0
    face_value: int = 0
    pre_issued_shares: int = 0
    method: str = ""
    issue_price: int = 0
    confirmed_price: int | None = None
    record_date: str | None = None
    shares_per_old: float | None = None
    subscription_date: str | None = None
    payment_date: str | None = None
    listing_date: str | None = None
    board_resolution_date: str | None = None


class BonusIssue(BaseDisclosure):
    """무상증자 결정 공시 데이터 도메인 모델.

    Attributes:
        disclosure_date (str): 실제 공시일.
        new_shares (int): 발행할 신주의 수.
        face_value (int): 1주당 액면가.
        pre_issued_shares (int): 증자 전 발행주식 총수.
        shares_per_old (float): 1주당 신주배정 주식수.
        record_date (str | None): 신주배정 기준일.
        listing_date (str | None): 신주 상장 예정일.
        capital_reserve (str): 증자 재원.
        board_resolution_date (str | None): 이사회 결의일.
    """

    disclosure_date: str
    new_shares: int = 0
    face_value: int = 0
    pre_issued_shares: int = 0
    shares_per_old: float = 0.0
    record_date: str | None = None
    listing_date: str | None = None
    capital_reserve: str = ""
    board_resolution_date: str | None = None


class ConvertibleBond(FundingDisclosure):
    """전환사채(CB) 발행 결정 공시 데이터 도메인 모델.

    Attributes:
        bond_round (str): 사채 회차.
        bond_type (str): 사채의 종류.
        bond_amount (int): 권면 총액.
        maturity_date (str | None): 사채 만기일.
        issue_method (str): 발행 방법 (사모/공모 등).
        conversion_ratio (float): 전환 비율 (%).
        conversion_price (int): 전환 가액.
        new_shares (int): 전환에 따라 발행할 주식수.
        shares_ratio (float): 주식총수 대비 비율.
        exercise_start_date (str | None): 전환청구 시작일.
        exercise_end_date (str | None): 전환청구 종료일.
        subscription_date (str | None): 청약일.
        payment_date (str | None): 납입일.
        board_resolution_date (str | None): 이사회 결의일.
    """

    bond_round: str = ""
    bond_type: str = ""
    bond_amount: int = 0
    maturity_date: str | None = None
    issue_method: str = ""
    conversion_ratio: float = 100.0
    conversion_price: int = 0
    new_shares: int = 0
    shares_ratio: float = 0.0
    exercise_start_date: str | None = None
    exercise_end_date: str | None = None
    subscription_date: str | None = None
    payment_date: str | None = None
    board_resolution_date: str | None = None


class BondWithWarrants(FundingDisclosure):
    """신주인수권부사채(BW) 발행 결정 공시 데이터 도메인 모델.

    Attributes:
        bond_round (str): 사채 회차.
        bond_type (str): 사채의 종류.
        bond_amount (int): 권면 총액.
        maturity_date (str | None): 사채 만기일.
        issue_method (str): 발행 방법 (사모/공모 등).
        warrant_ratio (float): 신주인수권 비율 (%).
        exercise_price (int): 행사 가액.
        new_shares (int): 행사에 따라 발행할 주식수.
        shares_ratio (float): 주식총수 대비 비율.
        exercise_start_date (str | None): 권리행사 시작일.
        exercise_end_date (str | None): 권리행사 종료일.
        subscription_date (str | None): 청약일.
        payment_date (str | None): 납입일.
        board_resolution_date (str | None): 이사회 결의일.
    """

    bond_round: str = ""
    bond_type: str = ""
    bond_amount: int = 0
    maturity_date: str | None = None
    issue_method: str = ""
    warrant_ratio: float = 100.0
    exercise_price: int = 0
    new_shares: int = 0
    shares_ratio: float = 0.0
    exercise_start_date: str | None = None
    exercise_end_date: str | None = None
    subscription_date: str | None = None
    payment_date: str | None = None
    board_resolution_date: str | None = None


class NewListing(BaseModel):
    """신규상장주(IPO) 분석 정보를 담는 모델.

    Attributes:
        listing_date (str): 상장일 (YYYY-MM-DD).
        name (str): 종목명.
        ticker (str | None): 종목 코드 (티커).
        sector (str | None): 업종.
        offer_price (int): 확정 공모 가액.
        lead_manager (str | None): 주간 금융투자업자(주간사).
        institutional_competition (float): 기관 투자자 경쟁률.
        mandatory_retention_pct (float): 의무보유확약 비율 (%).
        float_shares_pct (float): 유통 가능 물량 비율 (%).
        listing_day_open (int): 상장 당일 시가.
        listing_day_high (int): 상장 당일 고가.
        listing_day_low (int): 상장 당일 저가.
        listing_day_close (int): 상장 당일 종가.
        listing_day_change_pct (float): 상장 당일 등락률 (%).
        note (str | None): 비고/참고사항.
    """

    listing_date: str
    name: str
    ticker: str | None = None
    sector: str | None = None
    offer_price: int = 0
    lead_manager: str | None = None
    institutional_competition: float = 0.0
    mandatory_retention_pct: float = 0.0
    float_shares_pct: float = 0.0
    listing_day_open: int = 0
    listing_day_high: int = 0
    listing_day_low: int = 0
    listing_day_close: int = 0
    listing_day_change_pct: float = 0.0
    note: str | None = None
