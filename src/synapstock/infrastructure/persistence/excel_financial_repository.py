import pandas as pd
from ...domain.financials.models import FinancialMetric, FinancialStatement
from ...domain.financials.repository import FinancialRepository

class ExcelFinancialRepository(FinancialRepository):
    """엑셀 파일에서 재무제표 데이터를 읽어오는 저장소."""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        # 지표별 시트 인덱스 매핑 (분기 기준)
        self._metric_sheet_map = {
            FinancialMetric.REVENUE: 0,
            FinancialMetric.OPERATING_PROFIT: 1,
            FinancialMetric.NET_INCOME: 2
        }

    def get_all_quarters(self, metric: FinancialMetric) -> list[str]:
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
        quarters = self.get_all_quarters(metric)
        return quarters[0] if quarters else ""

    def load_all(self, metric: FinancialMetric) -> list[FinancialStatement]:
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
