import io
import logging

import pandas as pd

from synapstock.domain.statistics.models import BondWithWarrants, BonusIssue, ConvertibleBond, PaidInCapitalIncrease

from .base import BaseExcelParser

logger = logging.getLogger(__name__)


class DisclosureParser(BaseExcelParser):
    """유상/무상증자, 전환사채(CB), 신주인수권부사채(BW) 공시 데이터를 파싱하는 클래스."""

    def parse(self, content: bytes, **kwargs) -> list:
        """기본 parse 메서드. kwargs의 'type'에 따라 분기 처리하거나 리스트를 반환합니다.

        Args:
            content (bytes): 엑셀 파일 바이너리 데이터.
            **kwargs: 추가 옵션 (예: type).

        Returns:
            List: 파싱된 결과 리스트.
        """
        # 이 클래스는 하위 호환 및 개별 메서드 호출 위주로 사용됨
        return []

    def parse_paid_in_capital_increase(self, content: bytes) -> list[PaidInCapitalIncrease]:
        """엑셀 파일에서 유상증자 결정 공시 데이터를 파싱합니다.

        Args:
            content (bytes): 엑셀 파일 바이너리 데이터.

        Returns:
            List[PaidInCapitalIncrease]: 파싱된 유상증자 모델 리스트.
        """
        sheets_dict = pd.read_excel(io.BytesIO(content), sheet_name=None, header=None)
        results: list[PaidInCapitalIncrease] = []

        for sheet_name, df in sheets_dict.items():
            if df.empty:
                continue
            header_idx = self._find_header_row(df, "종목명")
            if header_idx == -1:
                continue

            new_df = df.iloc[header_idx + 1 :].copy()
            new_df.columns = [str(v).strip() for v in df.iloc[header_idx].values]

            for _, row in new_df.iterrows():
                try:
                    name_raw = self.get_val(row, "종목명", "종목")
                    if pd.isna(name_raw) or str(name_raw).strip() == "" or str(name_raw).strip() == "종목명":
                        continue

                    item = PaidInCapitalIncrease(
                        date=self.to_str(self.get_val(row, "일자", "일 시")),
                        name=self._clean_stock_name(self.to_str(name_raw)),
                        is_correction=str(self.get_val(row, "기재정정여부", "정정여부") or "").strip() == "Y"
                        or "정정" in str(self.get_val(row, "기재정정여부", "정정여부") or ""),
                        disclosure_date=self.to_str(self.get_val(row, "유상증자공시일", "공시일", "일자")),
                        rcp_no=self.to_str(self.get_val(row, "접수번호", "접수 번호")),
                        parent_rcp_no=(
                            self.to_str(self.get_val(row, "상위접수번호"))
                            if not pd.isna(self.get_val(row, "상위접수번호"))
                            else None
                        ),
                        new_shares=self.to_int(self.get_val(row, "신주발행주식수", "신주발행수", "발행배정주식수")),
                        face_value=self.to_int(self.get_val(row, "1주당 액면가", "1주당 액면가액", "액면가")),
                        pre_issued_shares=self.to_int(self.get_val(row, "증자전 발행주식총수", "증자전 발행주식 총수")),
                        fund_facility=self.to_int(self.get_val(row, "시설자금", "시설 자금")),
                        fund_operation=self.to_int(self.get_val(row, "운영자금", "운영 자금")),
                        fund_acquisition_biz=self.to_int(self.get_val(row, "영업양수자금", "영업 양수")),
                        fund_acquisition_sec=self.to_int(self.get_val(row, "타법인증권", "타법인 취득자금", "타법인")),
                        fund_debt_repayment=self.to_int(self.get_val(row, "채무상환자금", "채무 상환")),
                        fund_etc=self.to_int(self.get_val(row, "기타자금", "기타 자금")),
                        method=self.to_str(self.get_val(row, "증자방식", "증자 방식")),
                        issue_price=self.to_int(self.get_val(row, "신주의 발행가액", "발행가액", "발행가격")),
                        confirmed_price=self.to_int(self.get_val(row, "발행확정가액", "확정가액"))
                        if not pd.isna(self.get_val(row, "발행확정가액", "확정가액"))
                        else None,
                        record_date=self.to_str(self.get_val(row, "신주배정기준일", "기준일")),
                        shares_per_old=self.to_float(
                            self.get_val(row, "1주당 신주배정주식수", "배정비율", "1주당배정주식수")
                        ),
                        subscription_date=self.to_str(self.get_val(row, "청약예정일", "청약일")),
                        payment_date=self.to_str(self.get_val(row, "납입일")),
                        listing_date=self.to_str(self.get_val(row, "신주상장일", "상장일", "상장예정일")),
                        board_resolution_date=self.to_str(self.get_val(row, "이사회결의일", "결의일")),
                        initial_disclosure_date=self.to_str(self.get_val(row, "최초공시일", "최초 공시일")),
                    )
                    results.append(item)
                except Exception as e:
                    logger.error(f"[DisclosureParser] 유상증자 파싱 실패: {e}")
        return results

    def parse_bonus_issue(self, content: bytes) -> list[BonusIssue]:
        """엑셀 파일에서 무상증자 결정 공시 데이터를 파싱합니다.

        Args:
            content (bytes): 엑셀 파일 바이너리 데이터.

        Returns:
            List[BonusIssue]: 파싱된 무상증자 모델 리스트.
        """
        sheets_dict = pd.read_excel(io.BytesIO(content), sheet_name=None, header=None)
        results: list[BonusIssue] = []

        for sheet_name, df in sheets_dict.items():
            if df.empty:
                continue
            header_idx = self._find_header_row(df, "종목명")
            if header_idx == -1:
                continue

            new_df = df.iloc[header_idx + 1 :].copy()
            new_df.columns = [str(v).strip() for v in df.iloc[header_idx].values]

            for _, row in new_df.iterrows():
                try:
                    name_raw = self.get_val(row, "종목명", "종목")
                    if pd.isna(name_raw) or str(name_raw).strip() == "" or str(name_raw).strip() == "종목명":
                        continue

                    item = BonusIssue(
                        date=self.to_str(self.get_val(row, "일자", "일 시", "공시일")),
                        name=self._clean_stock_name(self.to_str(name_raw)),
                        is_correction=str(self.get_val(row, "기재정정여부", "정정여부") or "").strip() == "Y"
                        or "정정" in str(self.get_val(row, "기재정정여부", "정정여부") or ""),
                        disclosure_date=self.to_str(
                            self.get_val(row, "무상증자공시일", "공시일", "일자", "최초공시일")
                        ),
                        rcp_no=self.to_str(self.get_val(row, "접수번호", "접수 번호")),
                        parent_rcp_no=(
                            self.to_str(self.get_val(row, "상위접수번호"))
                            if not pd.isna(self.get_val(row, "상위접수번호"))
                            else None
                        ),
                        new_shares=self.to_int(
                            self.get_val(row, "신주발행주식수", "신주의 종류와 수", "신주수", "발행배정주식수")
                        ),
                        face_value=self.to_int(
                            self.get_val(row, "1주당 액면가액", "1주당 액면가", "액면가", "액면가액")
                        ),
                        pre_issued_shares=self.to_int(self.get_val(row, "증자전 발행주식총수", "증자전 발행주식 총수")),
                        shares_per_old=self.to_float(
                            self.get_val(row, "1주당 신주배정주식수", "1주당 신주배정 주식수", "배정비율")
                        ),
                        record_date=self.to_str(self.get_val(row, "신주배정기준일", "기준일")),
                        listing_date=self.to_str(
                            self.get_val(row, "신주상장일", "신주의 상장 예정일", "상장일", "상장예정일")
                        ),
                        capital_reserve=self.to_str(self.get_val(row, "무상증자 재원", "무상증자재원", "재원") or ""),
                        board_resolution_date=self.to_str(self.get_val(row, "이사회결의일", "결의일")),
                        initial_disclosure_date=self.to_str(self.get_val(row, "최초공시일", "최초 공시일")),
                    )
                    results.append(item)
                except Exception as e:
                    logger.error(f"[DisclosureParser] 무상증자 파싱 실패: {e}")
        return results

    def parse_convertible_bond(self, content: bytes) -> list[ConvertibleBond]:
        """엑셀 파일에서 전환사채(CB) 발행 결정 공시 데이터를 파싱합니다.

        Args:
            content (bytes): 엑셀 파일 바이너리 데이터.

        Returns:
            List[ConvertibleBond]: 파싱된 전환사채 모델 리스트.
        """
        sheets_dict = pd.read_excel(io.BytesIO(content), sheet_name=None, header=None)
        results: list[ConvertibleBond] = []

        for sheet_name, df in sheets_dict.items():
            if df.empty:
                continue
            header_idx = self._find_header_row(df, "상호", "종목명", "회사명")
            if header_idx == -1:
                continue

            new_df = df.iloc[header_idx + 1 :].copy()
            new_df.columns = [str(v).strip() for v in df.iloc[header_idx].values]

            for _, row in new_df.iterrows():
                try:
                    name_raw = self.get_val(row, "상호", "종목명", "회사명")
                    if pd.isna(name_raw) or str(name_raw).strip() == "" or str(name_raw).strip() in ["상호", "종목명"]:
                        continue

                    date_val = self.to_str(self.get_val(row, "공시일", "일자"))
                    if date_val and " " in date_val:
                        date_val = date_val.split(" ")[0]

                    item = ConvertibleBond(
                        date=date_val,
                        name=self._clean_stock_name(self.to_str(name_raw)),
                        is_correction="정정" in str(self.get_val(row, "기재정정여부", "정정여부") or ""),
                        bond_round=self.to_str(self.get_val(row, "회차", "회 차")),
                        bond_type=self.to_str(self.get_val(row, "종류", "채권종류")),
                        bond_amount=self.to_int(self.get_val(row, "권면총액", "사채의권면(전자등록)총액")),
                        fund_facility=self.to_int(self.get_val(row, "시설자금")),
                        fund_operation=self.to_int(self.get_val(row, "운영자금")),
                        fund_acquisition_biz=self.to_int(self.get_val(row, "영업양수자금")),
                        fund_acquisition_sec=self.to_int(self.get_val(row, "타법인증권", "타법인 증권")),
                        fund_debt_repayment=self.to_int(self.get_val(row, "채무상환자금")),
                        fund_etc=self.to_int(self.get_val(row, "기타자금")),
                        maturity_date=self.to_str(self.get_val(row, "사채의만기일", "만기일")),
                        issue_method=self.to_str(self.get_val(row, "사채발행방법", "발행방법")),
                        conversion_ratio=self.to_float(self.get_val(row, "전환비율")),
                        conversion_price=self.to_int(self.get_val(row, "전환가액")),
                        new_shares=self.to_int(self.get_val(row, "전환에따라발행할주식수", "전환주식수")),
                        shares_ratio=self.to_float(self.get_val(row, "주식총수대비비율", "총수대비비율")),
                        exercise_start_date=self.to_str(self.get_val(row, "전환청구기간시작일", "행사시작일")),
                        exercise_end_date=self.to_str(self.get_val(row, "전환청구기간종료일", "행사종료일")),
                        subscription_date=self.to_str(self.get_val(row, "청약일")),
                        payment_date=self.to_str(self.get_val(row, "납입일")),
                        board_resolution_date=self.to_str(self.get_val(row, "이사회결의일", "결의일")),
                        rcp_no=self.to_str(self.get_val(row, "접수번호")),
                        parent_rcp_no=self.to_str(self.get_val(row, "상위접수번호"))
                        if not pd.isna(self.get_val(row, "상위접수번호"))
                        else None,
                        initial_disclosure_date=self.to_str(self.get_val(row, "최초공시일")),
                    )
                    results.append(item)
                except Exception as e:
                    logger.error(f"[DisclosureParser] 전환사채 파싱 실패: {e}")
        return results

    def parse_bond_with_warrants(self, content: bytes) -> list[BondWithWarrants]:
        """엑셀 파일에서 신주인수권부사채(BW) 발행 결정 공시 데이터를 파싱합니다.

        Args:
            content (bytes): 엑셀 파일 바이너리 데이터.

        Returns:
            List[BondWithWarrants]: 파싱된 BW 모델 리스트.
        """
        sheets_dict = pd.read_excel(io.BytesIO(content), sheet_name=None, header=None)
        results: list[BondWithWarrants] = []

        for sheet_name, df in sheets_dict.items():
            if df.empty:
                continue
            header_idx = self._find_header_row(df, "상호", "종목명", "회사명")
            if header_idx == -1:
                continue

            new_df = df.iloc[header_idx + 1 :].copy()
            new_df.columns = [str(v).strip() for v in df.iloc[header_idx].values]

            for _, row in new_df.iterrows():
                try:
                    name_raw = self.get_val(row, "상호", "종목명", "회사명")
                    if pd.isna(name_raw) or str(name_raw).strip() == "" or str(name_raw).strip() in ["상호", "종목명"]:
                        continue

                    date_val = self.to_str(self.get_val(row, "공시일", "일자"))
                    if date_val and " " in date_val:
                        date_val = date_val.split(" ")[0]

                    item = BondWithWarrants(
                        date=date_val,
                        name=self._clean_stock_name(self.to_str(name_raw)),
                        is_correction="정정" in str(self.get_val(row, "기재정정여부", "정정여부") or ""),
                        bond_round=self.to_str(self.get_val(row, "회차", "회 차")),
                        bond_type=self.to_str(self.get_val(row, "종류", "채권종류")),
                        bond_amount=self.to_int(self.get_val(row, "권면총액", "사채의권면(전자등록)총액")),
                        fund_facility=self.to_int(self.get_val(row, "시설자금")),
                        fund_operation=self.to_int(self.get_val(row, "운영자금")),
                        fund_acquisition_biz=self.to_int(self.get_val(row, "영업양수자금")),
                        fund_acquisition_sec=self.to_int(self.get_val(row, "타법인증권", "타법인 증권")),
                        fund_debt_repayment=self.to_int(self.get_val(row, "채무상환자금")),
                        fund_etc=self.to_int(self.get_val(row, "기타자금")),
                        maturity_date=self.to_str(self.get_val(row, "사채의만기일", "만기일")),
                        issue_method=self.to_str(self.get_val(row, "사채발행방법", "발행방법")),
                        warrant_ratio=self.to_float(self.get_val(row, "신주인수권비율", "비율")),
                        exercise_price=self.to_int(self.get_val(row, "행사가액", "가격")),
                        new_shares=self.to_int(self.get_val(row, "행사에따라발행할주식수", "인수주식수")),
                        shares_ratio=self.to_float(self.get_val(row, "주식총수대비비율", "총수대비비율")),
                        exercise_start_date=self.to_str(self.get_val(row, "권리행사기간시작일", "행사시작일")),
                        exercise_end_date=self.to_str(self.get_val(row, "권리행사기간종료일", "행사종료일")),
                        subscription_date=self.to_str(self.get_val(row, "청약일")),
                        payment_date=self.to_str(self.get_val(row, "납입일")),
                        board_resolution_date=self.to_str(self.get_val(row, "이사회결의일", "결의일")),
                        rcp_no=self.to_str(self.get_val(row, "접수번호")),
                        parent_rcp_no=self.to_str(self.get_val(row, "상위접수번호"))
                        if not pd.isna(self.get_val(row, "상위접수번호"))
                        else None,
                        initial_disclosure_date=self.to_str(self.get_val(row, "최초공시일")),
                    )
                    results.append(item)
                except Exception as e:
                    logger.error(f"[DisclosureParser] BW 파싱 실패: {e}")
        return results

    def _find_header_row(self, df: pd.DataFrame, *target_keywords: str) -> int:
        """상단 15줄 이내에서 특정 키워드가 포함된 헤더 행의 인덱스를 찾습니다."""
        for i in range(min(15, len(df))):
            row_values = [str(v).strip() for v in df.iloc[i].values if not pd.isna(v)]
            if any(any(kw in v for kw in target_keywords) for v in row_values):
                return i
        return -1
