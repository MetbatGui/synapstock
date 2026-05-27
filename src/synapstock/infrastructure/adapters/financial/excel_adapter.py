from pathlib import Path
from typing import Any

import pandas as pd

from synapstock.domain.ports import FinancialDataPort


class ExcelFinancialDataAdapter(FinancialDataPort):
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self._sheets: dict[str, pd.DataFrame] = {}  # 시트별 캐시

    def _load_sheet(self, sheet_name: str) -> pd.DataFrame | None:
        if sheet_name not in self._sheets:
            if not self.file_path.exists():
                raise FileNotFoundError(f"Financial data file not found: {self.file_path}")

            try:
                # 특정 시트 로드
                df = pd.read_excel(self.file_path, sheet_name=sheet_name)
                # 첫 번째 컬럼 이름을 'company_name'으로 변경
                df.rename(columns={df.columns[0]: "company_name"}, inplace=True)
                self._sheets[sheet_name] = df
            except Exception as e:
                import logging

                logging.getLogger(__name__).error(f"Failed to load sheet {sheet_name}: {e}")
                return None

        return self._sheets.get(sheet_name)

    def get_financial_data(
        self, company_name: str, metric: str = "매출액", period: str = "분기별"
    ) -> list[dict[str, Any]]:
        """
        특정 기업의 재무 데이터를 리스트 형태로 반환합니다.
        지표(metric)와 기간(period)에 따라 해당 시트에서 데이터를 조회합니다.
        연간 데이터가 없는 경우 분기별 데이터를 합산하여 유사 연간 데이터를 생성합니다.
        """
        # 시트 이름 보정 (분기별 -> 분기)
        period_suffix = "분기" if period == "분기별" else period
        sheet_name = f"{metric}_{period_suffix}"
        df = self._load_sheet(sheet_name)

        # 1. 연간 데이터를 요청했으나 시트가 없거나 기업 정보가 없는 경우 분기 합산 시도
        if period == "연간":
            is_empty = df is None or df[df["company_name"] == company_name].empty
            if is_empty:
                return self._get_pseudo_annual_data(company_name, metric)

        if df is None:
            return []

        # 기업명으로 행 필터링
        row = df[df["company_name"] == company_name]
        if row.empty:
            return []

        result = []
        # 'company_name' 컬럼을 제외한 모든 컬럼(시기)을 순회
        for col in df.columns[1:]:
            val = row[col].values[0]
            # 숫자인 경우 정수형으로 변환 (보기 좋게)
            if pd.notna(val):
                if isinstance(val, (float, int)):
                    val = int(val)
                result.append({"quarter": str(col), "value": val})
            else:
                # 데이터가 없는 경우 None으로 추가
                result.append({"quarter": str(col), "value": None})

        return result

    def _get_pseudo_annual_data(self, company_name: str, metric: str) -> list[dict[str, Any]]:
        """분기 데이터를 합산하여 연간 데이터를 생성합니다."""
        quarterly_data = self.get_financial_data(company_name, metric, "분기별")
        if not quarterly_data:
            return []

        year_sums: dict[str, int] = {}
        for item in quarterly_data:
            if item["value"] is None:
                continue

            # "2023.1Q" 또는 "2023.3" 등의 형식에서 연도만 추출
            quarter_label = item["quarter"]
            year = quarter_label.split(".")[0]

            if year.isdigit() or (year.startswith("20") and len(year) == 4):
                year_sums[year] = year_sums.get(year, 0) + item["value"]

        # 연도순으로 정렬하여 반환
        result = []
        for year in sorted(year_sums.keys()):
            result.append({"quarter": str(year), "value": year_sums[year]})

        return result
