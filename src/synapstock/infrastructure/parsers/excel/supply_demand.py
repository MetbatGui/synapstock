import io
import logging

import pandas as pd

from synapstock.domain.statistics.models import (
    DailyMarketRanking,
    MarketType,
    MonthlyMarketStats,
    RankingItem,
    SupplySubject,
)

from .base import BaseExcelParser

logger = logging.getLogger(__name__)


class SupplyDemandParser(BaseExcelParser):
    """일별/월별 수급 순위 표를 파싱하는 클래스."""

    def parse(self, content: bytes, **kwargs) -> list[DailyMarketRanking]:
        """기본 parse 메서드. 종합 수급표 파싱을 수행합니다."""
        sheet_name = kwargs.get("sheet_name")
        date = kwargs.get("date")
        if not sheet_name or not date:
            return []
        return self.parse_summary_table(content, sheet_name, date)

    def parse_daily_ranking(
        self, content: bytes, market: MarketType, subject: SupplySubject, date: str
    ) -> DailyMarketRanking:
        df = pd.read_excel(io.BytesIO(content))
        items: list[RankingItem] = []
        for i, (_, row) in enumerate(df.iterrows()):
            if i >= 30:
                break
            name = self._clean_stock_name(str(row.iloc[0]))
            amount = self.to_int(row.iloc[1])
            items.append(RankingItem(rank=i + 1, name=name, amount=amount))

        return DailyMarketRanking(date=date, market=market, subject=subject, items=items)

    def parse_summary_table(self, content: bytes, sheet_name: str, date: str) -> list[DailyMarketRanking]:
        df = pd.read_excel(io.BytesIO(content), sheet_name=sheet_name, header=None)
        configs = [
            (4, 5, 6, MarketType.KOSPI, SupplySubject.FOREIGN),
            (8, 9, 10, MarketType.KOSPI, SupplySubject.INSTITUTION),
            (13, 14, 15, MarketType.KOSDAQ, SupplySubject.FOREIGN),
            (17, 18, 19, MarketType.KOSDAQ, SupplySubject.INSTITUTION),
        ]
        results: list[DailyMarketRanking] = []
        for name_col, amt_col, high_col, market, subject in configs:
            ranking = self._parse_ranking_category(df, name_col, amt_col, high_col, market, subject, date)
            results.append(ranking)
        return results

    def _parse_ranking_category(
        self,
        df: pd.DataFrame,
        name_col: int,
        amt_col: int,
        high_col: int,
        market: MarketType,
        subject: SupplySubject,
        date: str,
    ) -> DailyMarketRanking:
        start_row = 4
        num_items = 30
        items: list[RankingItem] = []

        for i in range(num_items):
            row_idx = start_row + i
            if row_idx >= len(df):
                break
            name_raw = df.iloc[row_idx, name_col]
            amount_raw = df.iloc[row_idx, amt_col]
            high_val_raw = df.iloc[row_idx, high_col]

            if pd.isna(name_raw) or str(name_raw).strip() == "":
                continue

            items.append(
                RankingItem(
                    rank=i + 1,
                    name=self._clean_stock_name(str(name_raw)),
                    amount=self.to_int(amount_raw),
                    high_price_type=(
                        str(high_val_raw).strip()
                        if not pd.isna(high_val_raw) and str(high_val_raw).strip() not in ("nan", "")
                        else None
                    ),
                )
            )
        return DailyMarketRanking(date=date, market=market, subject=subject, items=items)

    def parse_monthly_stats(
        self, content: bytes, market: MarketType, subject: SupplySubject, month: str
    ) -> MonthlyMarketStats:
        xl = pd.ExcelFile(io.BytesIO(content))
        sheet_name = self._find_monthly_sheet(xl.sheet_names, month)
        df = pd.read_excel(xl, sheet_name=sheet_name, header=None)

        start_row = 0
        for idx, row in df.iterrows():
            if "종목명" in str(row.values):
                start_row = idx + 1
                break

        items: list[RankingItem] = []
        for i in range(start_row, len(df)):
            item = self._parse_monthly_row(df.iloc[i], len(items) + 1)
            if item:
                items.append(item)
            if len(items) >= 100:
                break

        return MonthlyMarketStats(month=month, market=market, subject=subject, items=items)

    def _find_monthly_sheet(self, sheet_names: list[str], month: str) -> str:
        target_month_num = month[-2:]
        month_abbrs = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
        for name in sheet_names:
            if target_month_num in name or any(m in name.upper() for m in month_abbrs):
                return name
        return sheet_names[-1]

    def _parse_monthly_row(self, row: pd.Series, rank: int) -> RankingItem | None:
        name_raw = row.iloc[0]
        if pd.isna(name_raw) or str(name_raw).strip() in ("", "nan"):
            return None
        amount_raw = row.iloc[1] if len(row) > 1 else 0
        return RankingItem(rank=rank, name=self._clean_stock_name(str(name_raw)), amount=self.to_int(amount_raw))
