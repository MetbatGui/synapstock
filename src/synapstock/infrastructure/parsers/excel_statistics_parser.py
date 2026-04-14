import io
import logging
import re
from typing import Any

import pandas as pd

from synapstock.domain.statistics.models import (
    CeilingAnalysisReport,
    CeilingItem,
    DailyMarketRanking,
    MarketType,
    MonthlyMarketStats,
    PaidInCapitalIncrease,
    RankingItem,
    SupplySubject,
)

logger = logging.getLogger(__name__)

class ExcelStatisticsParser:
    """엑셀 통계 파일(수급 순위, 상한가 등)을 도메인 모델로 변환하는 파서 클래스."""

    @staticmethod
    def _clean_stock_name(name: str) -> str:
        """종목명에서 '(쌍)', '(씽)', '(상)' 등의 노이즈 문자를 제거합니다.

        엑셀 수기 작성 시 '삼성전자 (쌍)' 처럼 쌍끌이를 표시하는 텍스트가 포함될 경우,
        이를 순수 종목명 '삼성전자'로 원복하여 인덱싱 오류를 방지합니다.

        Args:
            name (str): 원본 종목명 데이터.

        Returns:
            str: 괄호 노이즈가 제거된 정제된 종목명.
        """
        name_str = str(name).strip()
        # 종목명 뒤에 공백과 함께 (쌍), (씽), (상) 등이 괄호로 붙은 경우 제거
        cleaned = re.sub(r"\s*\([쌍씽상]\)$", "", name_str)
        return cleaned.strip()

    @staticmethod
    def parse_daily_ranking(
        content: bytes, market: MarketType, subject: SupplySubject, date: str
    ) -> DailyMarketRanking:
        """특정 시장/주체의 일별 수급 순위 단일 엑셀 시트를 파싱합니다.

        Args:
            content (bytes): 엑셀 파일 바이너리 내용.
            market (MarketType): 대상 시장 (KOSPI/KOSDAQ).
            subject (SupplySubject): 대상 주체 (FOREIGN/INSTITUTION).
            date (str): 데이터의 기준 날짜 (YYYY-MM-DD).

        Returns:
            DailyMarketRanking: 파싱된 일별 수급 순위 도메인 모델.
        """
        df = pd.read_excel(io.BytesIO(content))

        # 엑셀 구조 분석 결과 (20260406코스피외인기관.xlsx):
        # 컬럼 0: 종목명, 컬럼 1: 순매수금액
        items: list[RankingItem] = []
        for i, (_, row) in enumerate(df.iterrows()):
            if i >= 30:
                break

            name = ExcelStatisticsParser._clean_stock_name(row.iloc[0])
            amount = int(row.iloc[1])

            items.append(RankingItem(
                rank=i + 1,
                name=name,
                amount=amount
            ))

        return DailyMarketRanking(
            date=date,
            market=market,
            subject=subject,
            items=items
        )

    @staticmethod
    def parse_summary_table(
        content: bytes, sheet_name: str, date: str
    ) -> list[DailyMarketRanking]:
        """하나의 시트에 4개 조합(시장 x 주체)이 포함된 종합 수급표를 파싱합니다.

        Args:
            content (bytes): 종합 엑셀 파일 바이너리 데이터.
            sheet_name (str): 파싱할 타겟 시트명 (예: "0408").
            date (str): 파싱 데이터에 부여할 기준 날짜 (YYYY-MM-DD).

        Returns:
            List[DailyMarketRanking]: 4가지(KOSPI/KOSDAQ x 외인/기관) 조합의 순위 리스트.
        """
        df = pd.read_excel(io.BytesIO(content), sheet_name=sheet_name, header=None)

        # 4개 카테고리 정의 (순서: 종목명 컬럼 index, 금액 컬럼 index, 신고가 컬럼 index, 시장, 주체)
        configs = [
            (4, 5, 6, MarketType.KOSPI, SupplySubject.FOREIGN),     # E, F, G
            (8, 9, 10, MarketType.KOSPI, SupplySubject.INSTITUTION),  # I, J, K
            (13, 14, 15, MarketType.KOSDAQ, SupplySubject.FOREIGN),   # N, O, P
            (17, 18, 19, MarketType.KOSDAQ, SupplySubject.INSTITUTION) # R, S, T
        ]

        results: list[DailyMarketRanking] = []
        for name_col, amt_col, high_col, market, subject in configs:
            ranking = ExcelStatisticsParser._parse_ranking_category(
                df, name_col, amt_col, high_col, market, subject, date
            )
            results.append(ranking)

        return results

    @staticmethod
    def _parse_ranking_category(
        df: pd.DataFrame,
        name_col: int,
        amt_col: int,
        high_col: int,
        market: MarketType,
        subject: SupplySubject,
        date: str
    ) -> DailyMarketRanking:
        """종합 수급표의 특정 카테고리(시장 x 주체) 데이터를 파싱합니다.

        Args:
            df (pd.DataFrame): 엑셀 시트 데이터프레임.
            name_col (int): 종목명이 위치한 컬럼 인덱스.
            amt_col (int): 매수 금액이 위치한 컬럼 인덱스.
            high_col (int): 신고가 정보가 위치한 컬럼 인덱스.
            market (MarketType): 시장 유형.
            subject (SupplySubject): 수급 주체.
            date (str): 기준 날짜.

        Returns:
            DailyMarketRanking: 파싱된 단일 카테고리의 수급 순위 데이터.
        """
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

            # 금액 정제
            amount = 0
            if not pd.isna(amount_raw):
                if isinstance(amount_raw, (int, float)):
                    amount = int(amount_raw)
                else:
                    cleaned = "".join(filter(str.isdigit, str(amount_raw)))
                    amount = int(cleaned) if cleaned else 0

            items.append(RankingItem(
                rank=i + 1,
                name=ExcelStatisticsParser._clean_stock_name(name_raw),
                amount=amount,
                high_price_type=(
                    str(high_val_raw).strip()
                    if not pd.isna(high_val_raw) and str(high_val_raw).strip() not in ("nan", "")
                    else None
                )
            ))

        return DailyMarketRanking(
            date=date,
            market=market,
            subject=subject,
            items=items
        )

    @staticmethod
    def parse_ceiling_report(
        content: bytes, title: str = "상한가 분석 리포트", sheet_name: str | None = None
    ) -> CeilingAnalysisReport:
        """상한가 분석 엑셀 파일을 파싱하여 도메인 모델로 변환합니다.

        Args:
            content (bytes): 엑셀 바이너리 데이터.
            title (str): 리포트 제목.
            sheet_name (Optional[str]): 시트명 (YYMMDD).

        Returns:
            CeilingAnalysisReport: 파싱된 리포트 모델.
        """
        df = pd.read_excel(io.BytesIO(content), sheet_name=sheet_name if sheet_name is not None else 0)

        # 1. 날짜 헤더 추출
        date_strs, date_cols = ExcelStatisticsParser._extract_ceiling_dates(df)

        logger.info(f"[ExcelStatisticsParser] 상한가 시트 파싱 시작: {sheet_name or '첫 번째 시트'}")
        logger.info(f"[ExcelStatisticsParser] 감지된 날짜 컬럼들({len(date_strs)}개): {date_strs}")

        # 2. 항목 파싱
        ceiling_items = []
        for _, row in df.iterrows():
            item = ExcelStatisticsParser._parse_ceiling_row(row, date_cols)
            if item:
                ceiling_items.append(item)

        # 3. 리포트 생성
        logger.info(f"[ExcelStatisticsParser] 파싱 완료: {len(ceiling_items)}개 종목 추출됨")

        return CeilingAnalysisReport(
            title=title,
            start_date=ExcelStatisticsParser._format_date(date_strs[0]) if date_strs else "",
            end_date=ExcelStatisticsParser._format_date(date_strs[-1]) if date_strs else "",
            dates=[f"{c[2:4]}-{c[4:6]}" for c in date_strs],
            items=ceiling_items,
            is_fully_collected=all(it.is_completed for it in ceiling_items) if ceiling_items else False
        )

    @staticmethod
    def _extract_ceiling_dates(df: pd.DataFrame) -> tuple[list[str], list[Any]]:
        """데이터프레임 헤더에서 날짜 정보(YYMMDD)가 담긴 컬럼들을 추출합니다.

        Args:
            df (pd.DataFrame): 엑셀 시트 데이터프레임.

        Returns:
            tuple[List[str], List[Any]]: (정렬된 날짜 문자열 리스트, 원본 컬럼 인덱스/객체 리스트).
        """
        date_pattern = re.compile(r"^(\d{6}|\d{8})$")
        date_cols_with_orig = []

        for col in df.columns:
            c_str = str(col).replace('.0', '').strip()
            if date_pattern.match(c_str):
                if len(c_str) == 8:
                    c_str = c_str[2:]
                date_cols_with_orig.append((c_str, col))

        date_cols_with_orig.sort(key=lambda x: x[0])
        return [d[0] for d in date_cols_with_orig], [d[1] for d in date_cols_with_orig]

    @staticmethod
    def _parse_ceiling_row(row: pd.Series, date_cols: list[Any]) -> CeilingItem | None:
        """상한가 분석 데이터의 단일 행을 파싱하여 도메인 모델로 변환합니다.

        Args:
            row (pd.Series): 엑셀의 단일 행 데이터.
            date_cols (List[Any]): 날짜 데이터가 포함된 컬럼 목록.

        Returns:
            Optional[CeilingItem]: 파싱된 항목 모델. 종목명이 없으면 None 반환.
        """
        name_val = row.iloc[0]
        if pd.isna(name_val) or str(name_val).strip() == "":
            return None

        # 가격 리스트 추출 (Forward Fill 적용)
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

        # 등락률 파싱 (마지막 컬럼)
        row.iloc[-1]

        return CeilingItem(
            name=ExcelStatisticsParser._clean_stock_name(str(name_val)),
            entry_tag=str(row.iloc[1]).strip() if not pd.isna(row.iloc[1]) else "",
            closing_prices=prices
        )

    @staticmethod
    def _parse_rate(val: Any) -> float:
        """문자열 또는 숫자형 등락률 데이터를 float로 변환합니다."""
        if pd.isna(val):
            return 0.0
        if isinstance(val, (int, float)):
            return float(val)
        cleaned = re.sub(r'[^0-9.-]', '', str(val))
        try:
            return float(cleaned) if cleaned else 0.0
        except ValueError:
            return 0.0

    @staticmethod
    def _format_date(yymmdd: str) -> str:
        """YYMMDD 형태의 날짜를 YYYY-MM-DD 형식으로 변환합니다."""
        if not yymmdd or len(yymmdd) < 6:
            return ""
        return f"20{yymmdd[:2]}-{yymmdd[2:4]}-{yymmdd[4:]}"

    @staticmethod
    def parse_monthly_stats(
        content: bytes,
        market: MarketType,
        subject: SupplySubject,
        month: str
    ) -> MonthlyMarketStats:
        """월간 누적 수급 엑셀 파일(APR 시트 등)을 파싱합니다.

        Args:
            content (bytes): 월간 통계 엑셀 파일 바이너리 데이터.
            market (MarketType): 시장 유형.
            subject (SupplySubject): 수급 주체.
            month (str): 기준 월 (예: "2026-04").

        Returns:
            MonthlyMarketStats: 파싱된 월간 누적 통계 데이터.
        """
        xl = pd.ExcelFile(io.BytesIO(content))
        sheet_name = ExcelStatisticsParser._find_monthly_sheet(xl.sheet_names, month)
        df = pd.read_excel(xl, sheet_name=sheet_name, header=None)

        # 데이터 시작 위치 탐색
        start_row = 0
        for idx, row in df.iterrows():
            if "종목명" in str(row.values):
                start_row = idx + 1
                break

        items: list[RankingItem] = []
        for i in range(start_row, len(df)):
            item = ExcelStatisticsParser._parse_monthly_row(df.iloc[i], len(items) + 1)
            if item:
                items.append(item)
            if len(items) >= 100:
                break

        return MonthlyMarketStats(
            month=month,
            market=market,
            subject=subject,
            items=items
        )

    @staticmethod
    def _find_monthly_sheet(sheet_names: list[str], month: str) -> str:
        """기준 월 정보(숫자 또는 약어)를 바탕으로 대상 시트명을 결정합니다.

        Args:
            sheet_names (List[str]): 엑셀 파일 내 전체 시트명 리스트.
            month (str): 기준 월 (YYYY-MM).

        Returns:
            str: 결정된 시트명. 매칭 실패 시 마지막 시트 반환.
        """
        target_month_num = month[-2:]
        month_abbrs = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

        for name in sheet_names:
            if target_month_num in name or any(m in name.upper() for m in month_abbrs):
                return name
        return sheet_names[-1]

    @staticmethod
    def _parse_monthly_row(row: pd.Series, rank: int) -> RankingItem | None:
        """월간 통계 데이터의 단일 행을 파싱하여 랭킹 모델로 변환합니다.

        Args:
            row (pd.Series): 엑셀의 단일 행 데이터.
            rank (int): 해당 종목에 부여할 순위.

        Returns:
            Optional[RankingItem]: 파싱된 랭킹 모델. 종목명이 없으면 None 반환.
        """
        name_raw = row.iloc[0]
        if pd.isna(name_raw) or str(name_raw).strip() in ("", "nan"):
            return None

        # 금액 컬럼 정제
        amount_raw = row.iloc[1] if len(row) > 1 else 0
        amount = 0
        if not pd.isna(amount_raw):
            if isinstance(amount_raw, (int, float)):
                amount = int(amount_raw)
            else:
                cleaned = "".join(filter(str.isdigit, str(amount_raw)))
                amount = int(cleaned) if cleaned else 0

        return RankingItem(
            rank=rank,
            name=ExcelStatisticsParser._clean_stock_name(str(name_raw)),
            amount=amount
        )

    @staticmethod
    def parse_paid_in_capital_increase(content: bytes) -> list[PaidInCapitalIncrease]:
        """유상증자 결정 엑셀 파일을 파싱하여 도메인 모델 리스트로 변환합니다.

        Args:
            content (bytes): 엑셀 바이너리 데이터.

        Returns:
            list[PaidInCapitalIncrease]: 파싱된 유상증자 데이터 리스트.
        """
        df = pd.read_excel(io.BytesIO(content))
        results: list[PaidInCapitalIncrease] = []

        # 칼럼 매핑 정의 (제공해주신 순서 및 이름 기준)
        # 일자, 종목명, 기재정정여부, 유상증자공시일, 접수번호, 상위접수번호, 신주발행주식수, 1주당 액면가, 증자전 발행주식총수,
        # 시설자금, 운영자금, 타법인증권, 기타자금, 증자방식, 신주의 발행가액, 발행확정가액, 신주배정기준일, 1주당 신주배정주식수,
        # 청약예정일, 납입일, 신주상장일, 이사회결의일, 최초공시일

        for _, row in df.iterrows():
            try:
                name_raw = row.get("종목명")
                if pd.isna(name_raw) or str(name_raw).strip() == "":
                    continue

                # 숫자 데이터 정제 함수
                def to_int(val: Any) -> int:
                    if pd.isna(val): return 0
                    if isinstance(val, (int, float)): return int(val)
                    cleaned = re.sub(r"[^0-9-]", "", str(val))
                    return int(cleaned) if cleaned else 0

                def to_float(val: Any) -> float:
                    if pd.isna(val): return 0.0
                    if isinstance(val, (int, float)): return float(val)
                    cleaned = re.sub(r"[^0-9.-]", "", str(val))
                    return float(cleaned) if cleaned else 0.0

                def to_str(val: Any) -> str:
                    return str(val).strip() if not pd.isna(val) else ""

                item = PaidInCapitalIncrease(
                    date=to_str(row.get("일자")),
                    name=ExcelStatisticsParser._clean_stock_name(to_str(name_raw)),
                    is_correction=str(row.get("기재정정여부")).strip() == "Y" or "정정" in str(row.get("기재정정여부")),
                    disclosure_date=to_str(row.get("유상증자공시일")),
                    rcp_no=to_str(row.get("접수번호")),
                    parent_rcp_no=to_str(row.get("상위접수번호")) or None,
                    new_shares=to_int(row.get("신주발행주식수")),
                    face_value=to_int(row.get("1주당 액면가")),
                    pre_issued_shares=to_int(row.get("증자전 발행주식총수")),
                    fund_facility=to_int(row.get("시설자금")),
                    fund_operation=to_int(row.get("운영자금")),
                    fund_acquisition=to_int(row.get("타법인증권")),
                    fund_etc=to_int(row.get("기타자금")),
                    method=to_str(row.get("증자방식")),
                    issue_price=to_int(row.get("신주의 발행가액")),
                    confirmed_price=to_int(row.get("발행확정가액")) if not pd.isna(row.get("발행확정가액")) else None,
                    record_date=to_str(row.get("신주배정기준일")),
                    shares_per_old=to_float(row.get("1주당 신주배정주식수")),
                    subscription_date=to_str(row.get("청약예정일")),
                    payment_date=to_str(row.get("납입일")),
                    listing_date=to_str(row.get("신주상장일")),
                    board_resolution_date=to_str(row.get("이사회결의일")),
                    initial_disclosure_date=to_str(row.get("최초공시일"))
                )
                results.append(item)
            except Exception as e:
                logger.error(f"[ExcelParser] 유상증자 행 파싱 실패: {e}")
                continue

        return results
