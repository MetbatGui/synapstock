import io
import logging
import re
from typing import Any

import pandas as pd

from synapstock.domain.statistics.models import CeilingAnalysisReport, CeilingItem

from .base import BaseExcelParser

logger = logging.getLogger(__name__)


class CeilingParser(BaseExcelParser):
    """상한가 분성 엑셀 리포트를 파싱하는 클래스."""

    def parse(self, content: bytes, **kwargs) -> CeilingAnalysisReport:
        """기본 parse 메서드. 상한가 리포트 파싱을 수행합니다."""
        title = kwargs.get("title", "상한가 분석 리포트")
        sheet_name = kwargs.get("sheet_name")
        return self.parse_ceiling_report(content, title, sheet_name)

    def parse_ceiling_report(
        self, content: bytes, title: str = "상한가 분석 리포트", sheet_name: str | None = None
    ) -> CeilingAnalysisReport:
        df = pd.read_excel(io.BytesIO(content), sheet_name=sheet_name if sheet_name is not None else 0)
        date_strs, date_cols = self._extract_ceiling_dates(df)

        ceiling_items = []
        for _, row in df.iterrows():
            item = self._parse_ceiling_row(row, date_cols)
            if item:
                ceiling_items.append(item)

        return CeilingAnalysisReport(
            title=title,
            start_date=self._format_date(date_strs[0]) if date_strs else "",
            end_date=self._format_date(date_strs[-1]) if date_strs else "",
            dates=[f"{c[2:4]}-{c[4:6]}" for c in date_strs] if date_strs else [],
            items=ceiling_items,
            is_fully_collected=all(it.is_completed for it in ceiling_items) if ceiling_items else False,
        )

    def _extract_ceiling_dates(self, df: pd.DataFrame) -> tuple[list[str], list[Any]]:
        date_pattern = re.compile(r"^(\d{6}|\d{8})$")
        date_cols_with_orig = []
        for col in df.columns:
            c_str = str(col).replace(".0", "").strip()
            if date_pattern.match(c_str):
                if len(c_str) == 8:
                    c_str = c_str[2:]
                date_cols_with_orig.append((c_str, col))
        date_cols_with_orig.sort(key=lambda x: x[0])
        return [d[0] for d in date_cols_with_orig], [d[1] for d in date_cols_with_orig]

    def _parse_ceiling_row(self, row: pd.Series, date_cols: list[Any]) -> CeilingItem | None:
        name_val = row.iloc[0]
        if pd.isna(name_val) or str(name_val).strip() == "":
            return None
        prices: list[int] = []
        for d_col in date_cols:
            price_val = row[d_col]
            if not pd.isna(price_val):
                try:
                    prices.append(int(float(price_val)))
                except (ValueError, TypeError):
                    prices.append(prices[-1] if prices else 0)
            else:
                prices.append(prices[-1] if prices else 0)
        return CeilingItem(
            name=self._clean_stock_name(str(name_val)),
            entry_tag=str(row.iloc[1]).strip() if not pd.isna(row.iloc[1]) else "",
            closing_prices=prices,
        )
