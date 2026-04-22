from pathlib import Path
from typing import Any

import pandas as pd


class ExcelFinancialDataAdapter:
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self._df: pd.DataFrame | None = None

    def _load_data(self):
        if self._df is None:
            if not self.file_path.exists():
                raise FileNotFoundError(f"Financial data file not found: {self.file_path}")
            # 전체 데이터를 로드 (캐싱)
            df = pd.read_excel(self.file_path)
            # 첫 번째 컬럼 이름을 'company_name'으로 변경
            df.rename(columns={df.columns[0]: "company_name"}, inplace=True)
            self._df = df

    def get_financial_data(self, company_name: str) -> list[dict[str, Any]]:
        """
        특정 기업의 분기별 재무 데이터를 리스트 형태로 반환합니다.
        [{"quarter": "2024.1Q", "value": 100}, ...]
        """
        self._load_data()

        if self._df is None:
            return []

        # 기업명으로 행 필터링
        row = self._df[self._df["company_name"] == company_name]
        if row.empty:
            return []

        result = []
        # 'company_name' 컬럼을 제외한 모든 컬럼(분기)을 순회
        for col in self._df.columns[1:]:
            val = row[col].values[0]
            # NaN이 아닌 경우에만 추가
            if pd.notna(val):
                # 숫자인 경우 정수형으로 변환 (보기 좋게)
                if isinstance(val, (float, int)):
                    val = int(val)
                result.append({"quarter": col, "value": val})

        return result
