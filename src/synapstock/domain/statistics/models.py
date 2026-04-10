from enum import Enum
from typing import List, Optional
from pydantic import BaseModel

class MarketType(str, Enum):
    KOSPI = "KOSPI"
    KOSDAQ = "KOSDAQ"

class SupplySubject(str, Enum):
    FOREIGN = "FOREIGN"      # 외국인
    INSTITUTION = "INSTITUTION"  # 기관

class RankingItem(BaseModel):
    """순위표의 개별 항목."""
    rank: int
    name: str
    amount: int  # 순매수 금액 (또는 거래량)
    ticker: Optional[str] = None  # 시스템 내 매칭된 티커
    high_price_type: Optional[str] = None  # 신고가 유형 약어 (예: 역·신, 52·근)

class DailyMarketRanking(BaseModel):
    """특정일, 특정 시장, 특정 주체의 수급 TOP 30."""
    date: str  # YYYY-MM-DD
    market: MarketType
    subject: SupplySubject
    items: List[RankingItem]

class MonthlyMarketStats(BaseModel):
    """월간 누적 수급 통계."""
    month: str  # YYYYMM
    market: MarketType
    subject: SupplySubject
    items: List[RankingItem]

# --- Analysis DTOs (조회 시점에 계산되는 뷰 모델) ---

class AnalyzedRankingItem(RankingItem):
    """순위 변동성 분석 정보가 포함된 개별 항목."""
    prev_rank: Optional[int] = None      # 이전 거래일 순위
    rank_change: Optional[int] = None    # 순위 변동폭 (이전-현재)
    consecutive_days: int = 1            # 연속 상위권 등장 횟수
    is_new: bool = False                 # 신규 진입 여부

class DailyMarketRankingAnalysis(BaseModel):
    """분석 정보가 포함된 특정일의 전체 수급 데이터."""
    date: str
    market: MarketType
    subject: SupplySubject
    items: List[AnalyzedRankingItem]
    previous_date: Optional[str] = None  # 비교 대상이 된 이전 거래일

# --- Ceiling Analysis Models (상한가 분석 모델) ---

class CeilingItem(BaseModel):
    """상한가 분석의 개별 종목 항목."""
    name: str              # 종목명
    entry_tag: str         # 진입 태그 (상, 52신 등)
    closing_prices: List[int] # 수집된 n거래일 종가 리스트
    change_rate: float     # 수익률 (단위: %)
    is_completed: bool     # 10개 일자 수집 완료 여부
    ticker: Optional[str] = None # 매칭된 티커

class CeilingAnalysisReport(BaseModel):
    """상한가 분석 전체 리포트 모델."""
    title: str             # 리포트 제목
    start_date: str        # 분석 대상 시작일 (YYYY-MM-DD)
    end_date: str          # 분석 대상 종료일 (YYYY-MM-DD)
    items: List[CeilingItem]
    is_fully_collected: bool # 전체 항목 완결 여부
