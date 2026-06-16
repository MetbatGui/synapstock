import io
import logging

import pandas as pd

from evenezer.domain.statistics.models import NewListing

from .base import BaseExcelParser

logger = logging.getLogger(__name__)


class NewListingParser(BaseExcelParser):
    """신규상장주(IPO) 분석 엑셀 파일을 파싱하는 클래스."""

    def parse(self, content: bytes, **kwargs) -> list[NewListing]:
        """연도별 신규상장주 엑셀 파일을 파싱하여 도메인 모델 리스트로 변환합니다.

        Args:
            content (bytes): 엑셀 파일 바이너리 데이터.
            **kwargs: 추가 옵션.

        Returns:
            List[NewListing]: 파싱된 신규상장주 모델 리스트 (중복 제거됨).
        """
        # 엑셀 내의 모든 시트를 순회하며 파싱 시도
        sheets_dict = pd.read_excel(io.BytesIO(content), sheet_name=None, header=None)

        # 중복 방지를 위한 딕셔너리 관리 (키: 종목명 + 상장일)
        results_dict: dict[tuple[str, str], NewListing] = {}

        for sheet_name, df in sheets_dict.items():
            if df.empty:
                continue

            # 헤더 행 찾기 ('종목명' 또는 '회사명' 포함 행)
            header_idx = self._find_header_row(df, "종목명", "회사명", "종목")
            if header_idx == -1:
                logger.debug(f"[NewListingParser] '{sheet_name}' 시트에서 헤더를 찾지 못했습니다.")
                continue

            new_df = df.iloc[header_idx + 1 :].copy()
            new_df.columns = [str(v).strip() for v in df.iloc[header_idx].values]

            for _, row in new_df.iterrows():
                try:
                    name_raw = self.get_val(row, "종목명", "회사명", "종목")
                    if (
                        pd.isna(name_raw)
                        or str(name_raw).strip() == ""
                        or str(name_raw).strip() in ["종목명", "회사명"]
                    ):
                        continue

                    # 데이터 정규화
                    listing_date = self.to_str(self.get_val(row, "상장일", "상장날짜", "일자"))
                    clean_name = self._clean_stock_name(self.to_str(name_raw))

                    if not listing_date or not clean_name:
                        continue

                    # 중복 체크 (이미 동일한 종목/날짜가 수집되었다면 스킵)
                    unique_key = (clean_name, listing_date)
                    if unique_key in results_dict:
                        continue

                    # IPO 데이터 확장 필드 파싱
                    item = NewListing(
                        listing_date=listing_date,
                        name=clean_name,
                        market=self.to_str(self.get_val(row, "시장구분", "시장")),
                        sector=self.to_str(self.get_val(row, "업종", "분류")),
                        face_value=self.to_int(self.get_val(row, "액면가")),
                        hope_price=self.to_str(self.get_val(row, "희망공모가액")),
                        offer_price=self.to_int(self.get_val(row, "확정공모가", "공모가")),
                        lead_manager=self.to_str(self.get_val(row, "주간사")),
                        institutional_competition=self.to_float(
                            self.get_val(row, "기관경쟁률", "경쟁률")
                        ),
                        employee_shares=self.to_int(self.get_val(row, "우리사주조합")),
                        inst_shares=self.to_int(self.get_val(row, "기관투자자")),
                        retail_shares=self.to_int(self.get_val(row, "일반청약자")),
                        float_shares_pct=self.to_float(self.get_val(row, "유통가능물량(%)", "유통비율")),
                        float_shares_vol=self.to_int(self.get_val(row, "유통가능물량(주)", "유통물량")),
                        total_offer_shares=self.to_int(self.get_val(row, "총공모주식수")),
                        offer_amount=self.to_int(self.get_val(row, "공모금액", "공모총액")),
                        revenue=self.to_int(self.get_val(row, "매출액")),
                        ebt=self.to_int(self.get_val(row, "법인세비용차감전")),
                        net_income=self.to_int(self.get_val(row, "순이익", "당기순이익")),
                        capital=self.to_int(self.get_val(row, "자본금")),
                        listing_day_open=self.to_int(self.get_val(row, "시가", "상장일시가")),
                        listing_day_high=self.to_int(self.get_val(row, "고가", "상장일고가")),
                        listing_day_low=self.to_int(self.get_val(row, "저가", "상장일저가")),
                        listing_day_close=self.to_int(self.get_val(row, "종가", "상장일종가")),
                        listing_day_change_pct=self.to_float(self.get_val(row, "수익률", "등락률")),
                        note=self.to_str(self.get_val(row, "비고")),
                    )
                    results_dict[unique_key] = item

                except Exception as e:
                    logger.error(f"[NewListingParser] '{sheet_name}' 시트 행 파싱 중 오류: {e}")

        return list(results_dict.values())

    def _find_header_row(self, df: pd.DataFrame, *target_keywords: str) -> int:
        """상단 15줄 이내에서 특정 키워드가 포함된 헤더 행의 인덱스를 찾습니다.

        Args:
            df (pd.DataFrame): 대상 데이터프레임.
            *target_keywords (str): 찾을 키워드 목록.

        Returns:
            int: 헤더 행의 인덱스. 찾지 못한 경우 -1.
        """
        for i in range(min(15, len(df))):
            row_values = [str(v).strip() for v in df.iloc[i].values if not pd.isna(v)]
            if any(any(kw in v for kw in target_keywords) for v in row_values):
                return i
        return -1
