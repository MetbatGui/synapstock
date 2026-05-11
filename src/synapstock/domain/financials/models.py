from enum import Enum
from pydantic import BaseModel

class FinancialMetric(Enum):
    """재무 지표 종류."""
    REVENUE = "매출"
    OPERATING_PROFIT = "영업이익"
    NET_INCOME = "당기순이익"

class FinancialStatement(BaseModel):
    """특정 종목의 시계열 재무 데이터."""
    stock_name: str
    values: dict[str, float]  # key: "2024.1Q", value: 금액

class FinancialAnalysisItem(BaseModel):
    """재무 분석 결과 항목."""
    stock_name: str
    current_value: float
    prev_value: float
    change_rate: float
