from pathlib import Path
from typing import Any

import pandas as pd

from evenezer.domain.ports import FinancialDataPort


class ExcelFinancialDataAdapter(FinancialDataPort):
    """Excel 파일 기반의 재무 데이터 제공 어댑터입니다.

    각 시트에서 기업들의 재무제표(매출액, 영업이익 등)를 분기/연간 단위로 읽어옵니다.
    """

    def __init__(self, file_path: Path):
        """ExcelFinancialDataAdapter를 초기화합니다.

        Args:
            file_path: 재무제표 Excel 파일 경로.
        """
        self.file_path = file_path
        self._sheets: dict[str, pd.DataFrame] = {}  # 시트별 캐시

    def _load_sheet(self, sheet_name: str) -> pd.DataFrame | None:
        """엑셀 파일에서 지정된 시트의 데이터를 Pandas DataFrame으로 로드합니다.

        Args:
            sheet_name: 로드할 엑셀 시트 이름.

        Returns:
            로드된 DataFrame 객체. 시트 로드 실패 시 None.

        Raises:
            FileNotFoundError: 지정된 경로에 엑셀 파일이 존재하지 않는 경우.
        """
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
        """특정 기업의 재무 지표 데이터를 시기순 목록으로 반환합니다.

        연간 데이터를 조회할 때 실제 연간 데이터 시트가 없으면, 분기별 데이터를 합산하여
        유사(pseudo) 연간 데이터를 구성하여 제공합니다.

        Args:
            company_name: 조회 대상 기업명.
            metric: 재무 지표 명칭 (예: '매출액', '영업이익'). 기본값은 '매출액'.
            period: 조회 주기 구분 ('연간', '분기별'). 기본값은 '분기별'.

        Returns:
            각 시기별 데이터 목록. 각 항목은 {"quarter": 시기 문자열, "value": 정수값 또는 None} 형태.
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
            # 숫자인 경우 Python 기본 int로 변환 (numpy scalar는 JSON 직렬화 불가)
            if pd.notna(val):
                if isinstance(val, (float, int)) or hasattr(val, "item"):
                    val = int(val) if not hasattr(val, "item") else int(val.item())
                result.append({"quarter": str(col), "value": val})
            else:
                # 데이터가 없는 경우 None으로 추가
                result.append({"quarter": str(col), "value": None})

        return result

    def _get_pseudo_annual_data(self, company_name: str, metric: str) -> list[dict[str, Any]]:
        """분기 데이터를 합산하여 연간 유사 데이터를 생성합니다.

        Args:
            company_name: 기업명.
            metric: 재무 지표 명칭.

        Returns:
            연도별로 합산된 재무 데이터 목록.
        """
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
