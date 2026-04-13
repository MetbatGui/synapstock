from enum import Enum
from typing import List, Optional
from pydantic import BaseModel

class MarketType(str, Enum):
    """주식 시장 유형 (KOSPI/KOSDAQ)."""
    KOSPI = "KOSPI"
    KOSDAQ = "KOSDAQ"

class SupplySubject(str, Enum):
    """수급 주체 유형 (외국인/기관)."""
    FOREIGN = "FOREIGN"      # 외국인
    INSTITUTION = "INSTITUTION"  # 기관

class RankingItem(BaseModel):
    """수급 순위표의 개별 종목 항목 모델.

    Attributes:
        rank (int): 해당 종목의 순위.
        name (str): 종목명.
        amount (int): 순매수 금액 또는 거래량.
        ticker (Optional[str]): 시스템 내 매칭된 티커 번호.
        high_price_type (Optional[str]): 신고가 유형 약어 (예: 역·신, 52·근).
    """
    rank: int
    name: str
    amount: int
    ticker: Optional[str] = None
    high_price_type: Optional[str] = None

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
    items: List[RankingItem]

class MonthlyMarketStats(BaseModel):
    """월간 누적 수급 통계 모델.

    Attributes:
        month (str): 기준 월 (YYYY-MM).
        market (MarketType): 시장 유형.
        subject (SupplySubject): 수급 주체.
        items (List[RankingItem]): 누적 순위 항목 리스트.
    """
    month: str
    market: MarketType
    subject: SupplySubject
    items: List[RankingItem]

# --- Analysis DTOs ---

class AnalyzedRankingItem(RankingItem):
    """순위 변동성 분석 정보가 포함된 확장 종목 모델.

    Attributes:
        prev_rank (Optional[int]): 이전 거래일의 순위.
        rank_change (Optional[int]): 순위 변동폭 (이전 - 현재).
        consecutive_days (int): 연속 상위권 등장 횟수.
        is_new (bool): 신규 진입 여부.
    """
    prev_rank: Optional[int] = None
    rank_change: Optional[int] = None
    consecutive_days: int = 1
    is_new: bool = False

class DailyMarketRankingAnalysis(BaseModel):
    """분석 정보가 포함된 상한가 리포트 분석 모델.

    Attributes:
        date (str): 기준 날짜.
        market (MarketType): 시장 유형.
        subject (SupplySubject): 수급 주체.
        items (List[AnalyzedRankingItem]): 분석 결과 포함 항목 리스트.
        previous_date (Optional[str]): 비교 대상이 된 이전 거래일 날짜.
    """
    date: str
    market: MarketType
    subject: SupplySubject
    items: List[AnalyzedRankingItem]
    previous_date: Optional[str] = None

# --- Ceiling Analysis Models ---

class CeilingItem(BaseModel):
    """상한가 분석의 개별 종목 항목 모델.

    Attributes:
        name (str): 종목명.
        entry_tag (str): 진입 시점의 태그 (상, 52신 등).
        closing_prices (List[int]): 수집된 n거래일 동안의 종가 리스트.
        change_rate (float): 기준일 대비 최종 수익률 (%).
        is_completed (bool): 10거래일 데이터 수집 완료 여부.
        ticker (Optional[str]): 매칭된 티커 번호.
    """
    name: str
    entry_tag: str
    closing_prices: List[int]
    change_rate: float
    is_completed: bool
    ticker: Optional[str] = None

class CeilingAnalysisReport(BaseModel):
    """상한가 분석 전체 리포트 모델.

    Attributes:
        title (str): 리포트 제목.
        start_date (str): 분석 대상 시작 거래일 (YYYY-MM-DD).
        end_date (str): 분석 대상 종료 거래일 (YYYY-MM-DD).
        dates (List[str]): 실제 데이터가 존재하는 날짜 목록 (MM-DD).
        items (List[CeilingItem]): 개별 상한가 종목 리스트.
        is_fully_collected (bool): 리포트 내 모든 종목의 수집 완결 여부.
    """
    title: str
    start_date: str
    end_date: str
    dates: List[str] = []
    items: List[CeilingItem]
    is_fully_collected: bool
