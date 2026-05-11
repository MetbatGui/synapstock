from typing import Protocol
from .models import FinancialMetric, FinancialStatement

class FinancialRepository(Protocol):
    """재무 데이터를 로드하는 저장소 인터페이스."""
    
    def load_all(self, metric: FinancialMetric) -> list[FinancialStatement]:
        """지정된 지표의 모든 종목 데이터를 로드합니다."""
        ...

    def get_latest_quarter(self, metric: FinancialMetric) -> str:
        """해당 지표에서 데이터가 존재하는 가장 최신 분기명을 반환합니다."""
        ...
