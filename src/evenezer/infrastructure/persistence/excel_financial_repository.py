import pandas as pd

from ...domain.financials.models import FinancialMetric, FinancialStatement
from ...domain.financials.repository import FinancialRepository


class ExcelFinancialRepository(FinancialRepository):
    """엑셀 파일에서 재무제표 데이터를 읽어오는 저장소."""

    def __init__(self, file_path: str):
        """ExcelFinancialRepository를 초기화합니다.

        Args:
            file_path: 재무제표 엑셀 파일 경로.
        """
        self.file_path = file_path
        # 지표별 시트 인덱스 매핑 (분기 기준)
        self._metric_sheet_map = {
            FinancialMetric.REVENUE: 0,
            FinancialMetric.OPERATING_PROFIT: 2,
            FinancialMetric.NET_INCOME: 4
        }

    def get_all_quarters(self, metric: FinancialMetric) -> list[str]:
        """특정 재무 지표에 대한 엑셀 시트로부터 전체 분기 목록을 조회하여 최신순(역순)으로 반환합니다.

        Args:
            metric: 조회할 재무 지표 구분 (매출액, 영업이익 등).

        Returns:
            분기 식별자 문자열 목록.
        """
        sheet_idx = self._metric_sheet_map.get(metric)
        if sheet_idx is None:
            return []
        try:
            df = pd.read_excel(self.file_path, sheet_name=sheet_idx, nrows=0)
            if len(df.columns) > 1:
                # 첫 번째 컬럼(종목명) 제외한 나머지 분기 목록을 역순(최신순)으로 반환
                return [str(c) for c in reversed(df.columns[1:])]
            return []
        except Exception:
            return []

    def get_latest_quarter(self, metric: FinancialMetric) -> str:
        """특정 재무 지표에 해당하는 엑셀 데이터 상의 가장 최근 분기 식별자를 반환합니다.

        Args:
            metric: 조회할 재무 지표 구분.

        Returns:
            최신 분기 식별 문자열. 데이터가 없을 경우 빈 문자열.
        """
        quarters = self.get_all_quarters(metric)
        return quarters[0] if quarters else ""

    def load_all(self, metric: FinancialMetric) -> list[FinancialStatement]:
        """특정 재무 지표에 대응하는 엑셀 데이터를 모두 로드하여 도메인 모델 목록으로 반환합니다.

        Args:
            metric: 조회 대상 재무 지표 구분.

        Returns:
            정제되어 복원된 FinancialStatement 도메인 인스턴스 목록.
        """
        sheet_idx = self._metric_sheet_map.get(metric)
        if sheet_idx is None:
            return []

        try:
            # 엑셀 파일 로드 (지정된 시트)
            df = pd.read_excel(self.file_path, sheet_name=sheet_idx)

            # 첫 번째 컬럼은 종목명, 나머지는 분기 데이터
            stock_col = df.columns[0]
            quarter_cols = df.columns[1:]

            statements = []
            for _, row in df.iterrows():
                stock_name = str(row[stock_col])
                # NaN을 제외한 유효한 데이터만 dict로 변환
                values = {
                    str(q): float(val)
                    for q, val in row[quarter_cols].items()
                    if pd.notnull(val)
                }

                if values:
                    statements.append(FinancialStatement(
                        stock_name=stock_name,
                        values=values
                    ))

            return statements
        except Exception as e:
            # 로깅은 추후 추가
            print(f"Error loading financials from excel: {e}")
            return []

    def get_last_modified_time(self) -> float:
        """엑셀 파일의 마지막 수정 시각(timestamp)을 조회합니다.

        Returns:
            수정 시각 timestamp, 파일 조회 불가 시 0.0.
        """
        import os
        try:
            return os.path.getmtime(self.file_path)
        except Exception:
            return 0.0
