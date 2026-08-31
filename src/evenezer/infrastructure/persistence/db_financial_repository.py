"""FinancialRepository 포트를 db/financial_statements.db(SQLite SSOT) 구독으로
구현한다.

다운로드는 별도 비동기 동기화 단계(container 부팅 시 1회, financial_db_sync
참고)가 미리 끝내둔다고 가정한다 - 이 클래스 자체는 이미 받아둔 로컬 파일을
동기적으로 읽기만 한다(FinancialService가 async 없이 동기 호출하므로).
"""

import os
from pathlib import Path

from evenezer.domain.financials.models import FinancialMetric, FinancialStatement
from evenezer.infrastructure.persistence import financial_db_query


class DbFinancialRepository:
    """재무 데이터를 SQLite SSOT 로컬 사본에서 로드하는 저장소."""

    def __init__(self, db_path: str):
        self.db_path = Path(db_path)

    def load_all(self, metric: FinancialMetric) -> list[FinancialStatement]:
        if not self.db_path.exists():
            return []
        rows = financial_db_query.fetch_statements(self.db_path, metric.value)
        return [FinancialStatement(stock_name=r["stock_name"], values=r["values"]) for r in rows]

    def get_all_quarters(self, metric: FinancialMetric) -> list[str]:
        """실제 값이 하나라도 있는 분기만 반환한다.

        list_quarters()(원시 행 존재 여부)를 그대로 쓰면 안 된다 - 아직 공시가
        안 들어온 미래 분기도 회사별 '자리표시' 행(모든 지표 NULL)이 미리
        만들어져 있어서(실 Drive 데이터로 확인함), 그런 분기까지 "가용 분기"에
        포함되면 get_latest_quarter()가 데이터 없는 분기를 반환하게 된다.
        fetch_statements()는 값이 있는 분기만 키로 담으므로 그 결과에서 유도한다.
        """
        if not self.db_path.exists():
            return []
        statements = financial_db_query.fetch_statements(self.db_path, metric.value)
        quarters = {q for s in statements for q in s["values"]}
        return sorted(quarters, reverse=True)

    def get_latest_quarter(self, metric: FinancialMetric) -> str:
        quarters = self.get_all_quarters(metric)
        return quarters[0] if quarters else ""

    def get_last_modified_time(self) -> float:
        try:
            return os.path.getmtime(self.db_path)
        except OSError:
            return 0.0
