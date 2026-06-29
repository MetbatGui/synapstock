from enum import StrEnum

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, computed_field, model_validator


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

    @classmethod
    def aggregate_from_daily(cls, month: str, rankings: list[DailyMarketRanking]) -> "MonthlyMarketStats":
        """여러 일별 랭킹 데이터를 합산하여 월간 통계를 생성합니다.

        Args:
            month: 기준 월 (YYYY-MM).
            rankings: 합산할 일별 랭킹 리스트.

        Returns:
            합산된 MonthlyMarketStats 인스턴스.

        Raises:
            ValueError: rankings 리스트가 비어 있는 경우.
        """
        if not rankings:
            # 빈 리스트일 경우 기본값 반환 (첫 번째 인자의 마켓/주체 정보가 없으므로 호출자 책임)
            raise ValueError("rankings list cannot be empty for aggregation")

        market = rankings[0].market
        subject = rankings[0].subject

        # 종목별 금액 합산
        aggregation: dict[str, dict] = {}
        for r in rankings:
            for item in r.items:
                if item.name not in aggregation:
                    aggregation[item.name] = {"amount": 0, "ticker": item.ticker}
                aggregation[item.name]["amount"] += item.amount

        # 금액 기준 내림차순 정렬 및 TOP 30 추출
        sorted_items = sorted(aggregation.items(), key=lambda x: x[1]["amount"], reverse=True)[:30]

        items = []
        for i, (name, data) in enumerate(sorted_items, 1):
            items.append(RankingItem(rank=i, name=name, amount=data["amount"], ticker=data["ticker"]))

        return cls(month=month, market=market, subject=subject, items=items)


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
        market (str | None): 시장 구분 (예: 코스피, 코스닥).
        sector (str | None): 업종.
        face_value (int): 액면가.
        hope_price (str | None): 희망 공모 가액 범위.
        offer_price (int): 확정 공모 가액.
        lead_manager (str | None): 주간 금융투자업자(주간사).
        institutional_competition (float): 기관 투자자 경쟁률.
        employee_shares (int): 우리사주조합 배정 주식수.
        inst_shares (int): 기관투자자 배정 주식수.
        retail_shares (int): 일반청약자 배정 주식수.
        float_shares_pct (float): 유통 가능 물량 비율 (%).
        float_shares_vol (int): 유통 가능 물량 (주).
        total_offer_shares (int): 총 공모 주식수.
        offer_amount (int): 공모 금액 (백만원).
        revenue (int): 매출액 (백만원).
        ebt (int): 법인세비용차감전계속사업이익 (백만원).
        net_income (int): 순이익 (백만원).
        capital (int): 자본금 (백만원).
        listing_day_open (int): 상장 당일 시가.
        listing_day_high (int): 상장 당일 고가.
        listing_day_low (int): 상장 당일 저가.
        listing_day_close (int): 상장 당일 종가.
        listing_day_change_pct (float): 상장 당일 등락률 (%).
        current_price (int): 최신 현재가.
        current_change_pct (float): 최신 현재 수익률 (%).
        note (str | None): 비고/참고사항.
    """

    listing_date: str | None = None
    name: str
    ticker: str | None = None
    market: str | None = None
    sector: str | None = None
    face_value: int = 0
    hope_price: str | None = None
    offer_price: int = 0
    lead_manager: str | None = None
    institutional_competition: float = 0.0
    employee_shares: int = 0
    inst_shares: int = 0
    retail_shares: int = 0
    float_shares_pct: float = 0.0
    float_shares_vol: int = 0
    total_offer_shares: int = 0
    offer_amount: int = 0
    revenue: int = 0
    ebt: int = 0
    net_income: int = 0
    capital: int = 0
    listing_day_open: int = 0
    listing_day_high: int = 0
    listing_day_low: int = 0
    listing_day_close: int = 0
    listing_day_change_pct: float = 0.0
    current_price: int = Field(default=0)
    current_change_pct: float = Field(default=0.0)
    note: str | None = None
    status: str = "PENDING"
    current_board: str = "virtual_신규상장주"
    current_path: list[str] = Field(default_factory=list)
    updated_at: str | None = None

    def update_market_price(self, price: int) -> None:
        """최신 현재가 및 공모가 대비 수익률을 계산하여 상태를 보강합니다."""
        self.current_price = price
        if self.offer_price > 0:
            diff = price - self.offer_price
            self.current_change_pct = round((diff / self.offer_price) * 100, 2)
        else:
            self.current_change_pct = 0.0

    def merge_with(self, other: "NewListing") -> "NewListing":
        """비즈니스 우선순위 규칙에 근거하여 다른 IPO 정보와 병합한 최종 버전을 반환합니다.

        병합 규칙:
        1. ASSIGNED 상태가 최우선
        2. IGNORED 상태가 PENDING보다 우선
        3. 상태가 같은 경우 updated_at 타임스탬프가 최신인 쪽을 우선

        Args:
            other: 병합할 다른 NewListing 객체.

        Returns:
            병합 비즈니스 규칙이 적용된 최종 NewListing 인스턴스.
        """
        l_status = self.status
        r_status = other.status

        # 1. ASSIGNED 상태 최우선
        if l_status == "ASSIGNED" and r_status != "ASSIGNED":
            return self
        if r_status == "ASSIGNED" and l_status != "ASSIGNED":
            return other

        # 2. IGNORED 상태가 PENDING보다 우선
        if l_status == "IGNORED" and r_status == "PENDING":
            return self
        if r_status == "IGNORED" and l_status == "PENDING":
            return other

        # 3. 상태가 같으면 updated_at 최신성 우선
        l_updated = self.updated_at or ""
        r_updated = other.updated_at or ""
        if l_updated >= r_updated:
            return self
        return other


class WeeklyChangeItem(BaseModel):
    """주간 등락률의 개별 종목 항목 모델.

    Attributes:
        name (str): 종목명.
        ticker (str | None): 종목 코드.
        close_price (int): 종료일 종가 (최근 가격).
        base_price (int): 시작일 종가 (기준 가격).
        change_rate (float): 주간 등락률 (%).
    """

    name: str
    ticker: str | None = None
    close_price: int = Field(0, validation_alias=AliasChoices("close_price", "current_price"))
    base_price: int = Field(0, validation_alias=AliasChoices("base_price", "prev_week_close"))
    change_rate: float = 0.0


class WeeklyChangeReport(BaseModel):
    """주간 등락률 전체 리포트 모델.

    Attributes:
        date (str): 기준 일자 (보통 범위의 종료일, YYYY-MM-DD).
        year (int | None): 연도 (예: 2026).
        month (int | None): 월 (예: 5).
        week_of_month (int | None): 월간 주차 (예: 1).
        week_num (int | None): 연간 주차 (예: 19).
        date_range (str | None): 기간 (예: 0504~0508).
        items (list[WeeklyChangeItem]): 등락률 항목 리스트.
    """

    date: str
    year: int | None = None
    month: int | None = None
    week_of_month: int | None = None
    week_num: int | None = None
    date_range: str | None = None
    items: list[WeeklyChangeItem]


class StockSplit(BaseModel):
    """주식 분할(액면분할) 상세 정보를 나타내는 도메인 모델.

    Attributes:
        company_name (str): 회사명.
        market (str | None): 시장 (KOSPI/KOSDAQ 등).
        disclosure_type (str | None): 공시구분.
        base_date (str): 배정기준일 (YYYY-MM-DD 포맷 정규화).
        board_resolution_date (str | None): 이사회결의일 (YYYY-MM-DD 포맷 정규화).
        receipt_no (str): 접수번호 (14자리 고유 문자열, 고유 식별자).
        original_receipt_no (str | None): 원접수번호.
        prev_shares (int | None): 발행주식수(이전).
        post_shares (int | None): 발행주식수(이후).
        split_ratio (float | None): 분할비율.
        listing_date (str | None): 신주상장예정일 (YYYY-MM-DD 포맷 정규화).
        general_meeting_date (str | None): 주총결의일 (YYYY-MM-DD 포맷 정규화).
        first_disclosure_date (str | None): 최초공시 등록일자.
    """

    model_config = ConfigDict(frozen=True)

    company_name: str
    market: str | None = None
    disclosure_type: str | None = None
    base_date: str
    board_resolution_date: str | None = None
    receipt_no: str
    original_receipt_no: str | None = None
    prev_shares: int | None = None
    post_shares: int | None = None
    split_ratio: float | None = None
    listing_date: str | None = None
    general_meeting_date: str | None = None
    first_disclosure_date: str | None = None

    @model_validator(mode="after")
    def validate_business_rules(self) -> "StockSplit":
        """비즈니스 도메인 규칙을 자율 검증합니다.

        Returns:
            자기 자신(StockSplit) 인스턴스.

        Raises:
            ValueError: 회사명 또는 접수번호가 비어있거나, 분할 비율이 0 이하인 경우.
        """
        if not self.company_name.strip():
            raise ValueError("회사명은 필수값이며 비어 있을 수 없습니다.")
        if not self.receipt_no.strip():
            raise ValueError("접수번호는 필수값이며 비어 있을 수 없습니다.")
        if self.split_ratio is not None and self.split_ratio <= 0:
            raise ValueError("분할 비율은 0보다 커야 합니다.")
        return self

    @computed_field
    def rcp_no(self) -> str:
        return self.receipt_no

    @computed_field
    def parent_rcp_no(self) -> str | None:
        return self.original_receipt_no

    @computed_field
    def is_correction(self) -> bool:
        return self.original_receipt_no is not None and len(self.original_receipt_no.strip()) > 0


class StockSplitManifest(BaseModel):
    """주식 분할 동기화 상태를 추적하기 위한 매니페스트 모델.

    Attributes:
        manifest_version (str): 매니페스트 버전.
        last_updated (str): 마지막 동기화 일시.
        total_records (int): 전체 레코드 개수.
        supported_years (list[str]): 지원하는 연도 목록.
        years_index (dict[str, list[str]]): 연도별 접수번호(receipt_no) 목록 인덱스.
    """

    manifest_version: str
    last_updated: str
    total_records: int
    supported_years: list[str]
    years_index: dict[str, list[str]]
