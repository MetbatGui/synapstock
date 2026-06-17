from typing import Protocol

from .models import FinancialMetric, FinancialStatement


class FinancialRepository(Protocol):
    """재무 데이터를 로드하는 저장소 인터페이스."""

    def load_all(self, metric: FinancialMetric) -> list[FinancialStatement]:
        """지정된 지표의 모든 종목 데이터를 로드합니다.

        Args:
            metric: 로드할 재무 지표 구분 (REVENUE, OPERATING_PROFIT 등).

        Returns:
            각 종목별 시계열 재무 데이터 목록.
        """
        ...

    def get_latest_quarter(self, metric: FinancialMetric) -> str:
        """가장 최신 분기 문자열을 반환합니다.

        Args:
            metric: 대상 재무 지표 구분.

        Returns:
            최신 분기 명칭 (예: '2024.1Q').
        """
        ...

    def get_all_quarters(self, metric: FinancialMetric) -> list[str]:
        """선택 가능한 모든 분기 리스트를 반환합니다.

        Args:
            metric: 대상 재무 지표 구분.

        Returns:
            분기명 리스트 (예: ['2023.3Q', '2023.4Q', '2024.1Q']).
        """
        ...

    def get_last_modified_time(self) -> float:
        """데이터 소스의 마지막 수정 시각을 반환합니다.

        Returns:
            마지막 수정 시각의 Epoch 타임스탬프 값.
        """
        ...
