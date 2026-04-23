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

    def parse(self, content: bytes, **kwargs) -> list[CeilingAnalysisReport]:
        """기본 parse 메서드. 모든 시트를 파싱하여 목록으로 반환합니다."""
        title_base = kwargs.get("title", "상한가 분석 리포트")
        return self.parse_all_sheets(content, title_base)

    def parse_all_sheets(self, content: bytes, title_base: str = "상한가 분석 리포트") -> list[CeilingAnalysisReport]:
        """엑셀 파일 내의 모든 유효한 시트를 파싱합니다."""
        excel = pd.ExcelFile(io.BytesIO(content))
        reports = []

        for sheet_name in excel.sheet_names:
            # YYMMDD 형식의 시트만 처리
            if len(sheet_name) == 6 and sheet_name.isdigit():
                try:
                    df = pd.read_excel(excel, sheet_name=sheet_name)
                    report = self.parse_dataframe(df, f"{title_base} ({sheet_name})", sheet_name)
                    if report and report.items:
                        reports.append(report)
                except Exception as e:
                    logger.warning(f"시트 {sheet_name} 파싱 실패: {e}")

        return reports

    def parse_dataframe(self, df: pd.DataFrame, title: str, sheet_name: str) -> CeilingAnalysisReport:
        """단일 데이터프레임을 파싱하여 리포트 객체를 생성합니다."""
        date_strs, date_cols = self._extract_ceiling_dates(df)

        # 시트 이름이 YYMMDD 형식인 경우 처리
        is_sheet_date_valid = len(sheet_name) == 6 and sheet_name.isdigit()

        # 시트명 날짜가 컬럼에 없으면 강제로 추가 (시트 자체가 해당 날짜 리포트이므로)
        if is_sheet_date_valid and sheet_name not in date_strs:
            date_strs.append(sheet_name)
            # 만약 컬럼 매칭이 안 되었다면, 보통 시트의 마지막 수치 컬럼들을 가격으로 간주
            if not date_cols:
                # 첫 2개 컬럼(종목명, 태그) 제외한 나머지를 가격 컬럼으로 추정
                potential_cols = [c for c in df.columns[2:] if not str(c).startswith('Unnamed')]
                date_cols = potential_cols

        ceiling_items = []
        for _, row in df.iterrows():
            item = self._parse_ceiling_row(row, date_cols)
            if item:
                ceiling_items.append(item)

        # 최종 날짜 결정: 무조건 시트 이름을 우선시함
        if is_sheet_date_valid:
            end_date_str = self._format_date(sheet_name)
        else:
            end_date_str = self._format_date(date_strs[-1]) if date_strs else ""

        return CeilingAnalysisReport(
            title=title,
            start_date=self._format_date(date_strs[0]) if date_strs else end_date_str,
            end_date=end_date_str,
            dates=[f"{c[2:4]}-{c[4:6]}" for c in date_strs],
            items=ceiling_items,
            is_fully_collected=all(it.is_completed for it in ceiling_items) if ceiling_items else False,
        )

    def parse_ceiling_report(
        self, content: bytes, title: str = "상한가 분석 리포트", sheet_name: str | None = None
    ) -> CeilingAnalysisReport:
        # 기존 호환성 유지
        df = pd.read_excel(io.BytesIO(content), sheet_name=sheet_name if sheet_name is not None else 0)
        return self.parse_dataframe(df, title, sheet_name or "Unknown")

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
