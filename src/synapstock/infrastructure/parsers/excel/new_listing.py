import io
import logging

import pandas as pd

from synapstock.domain.statistics.models import NewListing

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
            List[NewListing]: 파싱된 신규상장주 모델 리스트.
        """
        # 엑셀 내의 모든 시트를 순회하며 파싱 시도
        sheets_dict = pd.read_excel(io.BytesIO(content), sheet_name=None, header=None)
        results: list[NewListing] = []

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

                    # IPO 데이터 특화 필드 파싱 (사용자 제공 샘플 반영)
                    item = NewListing(
                        listing_date=self.to_str(self.get_val(row, "상장일", "상장날짜", "일자")),
                        name=self._clean_stock_name(self.to_str(name_raw)),
                        sector=self.to_str(self.get_val(row, "업종", "분류")),
                        offer_price=self.to_int(self.get_val(row, "확정공모가", "공모가", "발행가액")),
                        lead_manager=self.to_str(self.get_val(row, "주간사", "주간 증권사")),
                        institutional_competition=self.to_float(
                            self.get_val(row, "기관경쟁률", "경쟁률", "기관 경쟁률")
                        ),
                        mandatory_retention_pct=self.to_float(self.get_val(row, "의무보유확약", "확약비율", "확약")),
                        float_shares_pct=self.to_float(self.get_val(row, "유통가능물량(%)", "유통비율", "유통물량")),
                        listing_day_open=self.to_int(self.get_val(row, "시가", "상장일시가")),
                        listing_day_high=self.to_int(self.get_val(row, "고가", "상장일고가")),
                        listing_day_low=self.to_int(self.get_val(row, "저가", "상장일저가")),
                        listing_day_close=self.to_int(self.get_val(row, "종가", "상장일종가")),
                        listing_day_change_pct=self.to_float(self.get_val(row, "수익률(%)", "등락률", "상장일등락률")),
                        note=self.to_str(self.get_val(row, "비고", "메모")),
                    )
                    results.append(item)
                except Exception as e:
                    logger.error(f"[NewListingParser] '{sheet_name}' 시트 행 파싱 중 오류: {e}")

        return results

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
