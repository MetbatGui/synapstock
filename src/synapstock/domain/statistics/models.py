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
