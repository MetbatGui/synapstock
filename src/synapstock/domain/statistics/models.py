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
