import io
import logging
import pandas as pd
from synapstock.domain.statistics.models import WeeklyChangeItem, WeeklyChangeReport
from .base import BaseExcelParser

logger = logging.getLogger(__name__)

class WeeklyChangeParser(BaseExcelParser):
    """주간 등락률 엑셀 파일을 파싱하는 클래스."""

    def extract_metadata_from_filename(self, filename: str) -> dict:
        """파일명에서 메타데이터를 추출합니다.
        
        예: 'weekly_gainers_2026_W19_05M1W_0504~0508.xlsx'
        """
        import re
        
        metadata = {
            "year": None,
            "month": None,
            "week_of_month": None,
            "week_num": None,
            "date_range": None,
            "date": "Unknown"
        }
        
        try:
            # 1. 연도 추출 (4자리 숫자)
            year_match = re.search(r"(\d{4})", filename)
            if year_match:
                metadata["year"] = int(year_match.group(1))
            
            # 2. 주차 추출 (W + 숫자)
            week_match = re.search(r"W(\d+)", filename)
            if week_match:
                metadata["week_num"] = int(week_match.group(1))
            
            # 3. 월 및 월간 주차 (MM + M + 숫자 + W) - 예: 05M1W
            mw_match = re.search(r"(\d{2})M(\d+)W", filename)
            if mw_match:
                metadata["month"] = int(mw_match.group(1))
                metadata["week_of_month"] = int(mw_match.group(2))
            
            # 4. 기간 추출 (0504~0508)
            range_match = re.search(r"(\d{4}~\d{4})", filename)
            if range_match:
                metadata["date_range"] = range_match.group(1)
                
                # 5. 기준일 설정 (종료일 기준, 예: 2026-05-08)
                if metadata["year"]:
                    end_date_str = range_match.group(1).split("~")[1] # 0508
                    metadata["date"] = f"{metadata['year']}-{end_date_str[:2]}-{end_date_str[2:]}"
                    
        except Exception as e:
            logger.warning(f"[WeeklyChangeParser] 파일명 메타데이터 추출 실패 ({filename}): {e}")
            
        return metadata

    def _find_value(self, row, keywords, default=None):
        """유니코드 정규화를 적용하여 정밀 매칭 후 부분 매칭을 시도합니다."""
        import unicodedata

        # 1. 완전 일치 시도 (정규화 포함)
        for col in row.index:
            col_norm = unicodedata.normalize("NFC", str(col)).strip().replace(" ", "").replace("\n", "")
            if col_norm in keywords:
                return row[col]
        
        # 2. 부분 일치 시도
        for col in row.index:
            col_norm = unicodedata.normalize("NFC", str(col)).strip().replace(" ", "").replace("\n", "")
            for kw in keywords:
                if kw in col_norm:
                    # '저가'가 '종가'로 매칭되는 것 방지
                    if kw == "종가" and "저가" in col_norm:
                        continue
                    return row[col]
        return default

    def parse(self, content: bytes, **kwargs) -> WeeklyChangeReport:
        """엑셀 내용을 파싱하여 WeeklyChangeReport를 반환합니다."""
        filename = kwargs.get("filename", "")
        metadata = self.extract_metadata_from_filename(filename)
        
        date = metadata["date"] if metadata["date"] != "Unknown" else kwargs.get("date", "Unknown")
        
        df = pd.read_excel(io.BytesIO(content))
        
        # 컬럼 키워드 (사용자 제공 형식 반영)
        name_kws = ["종목명", "Name"]
        curr_kws = ["종가", "현재가"]
        base_kws = ["기준가", "시가", "전주종가"]
        rate_kws = ["등락률", "주간등락률"]
        ticker_kws = ["종목코드", "코드", "Ticker"]

        items = []
        for _, row in df.iterrows():
            try:
                # 1. 종목명 및 티커 추출
                raw_name = self._find_value(row, name_kws)
                if raw_name is None: raw_name = row.iloc[0]
                name = self._clean_stock_name(str(raw_name))
                if not name or name == "nan" or "종목" in name: continue
                
                raw_ticker = self._find_value(row, ticker_kws)
                ticker = str(raw_ticker).strip().zfill(6) if raw_ticker is not None else None
                    
                # 2. 값 추출
                raw_curr = self._find_value(row, curr_kws)
                raw_base = self._find_value(row, base_kws)
                raw_rate = self._find_value(row, rate_kws, 0.0)

                # 등락률 정제
                if isinstance(raw_rate, str):
                    raw_rate = raw_rate.replace("+", "").replace("%", "").replace(",", "").strip()
                change_rate = self.to_float(raw_rate)
                
                # 현재가(종가) 및 기준가(기준가/시가) 정제
                current_price = self.to_int(raw_curr) if raw_curr is not None else 0
                base_price = self.to_int(raw_base) if raw_base is not None else 0
                
                # 기준가가 0이면 등락률로 역산 (백업용)
                if base_price == 0 and current_price > 0:
                    base_price = int(round(current_price / (1 + change_rate / 100)))
                
                items.append(WeeklyChangeItem(
                    name=name,
                    ticker=ticker,
                    close_price=current_price,
                    base_price=base_price,
                    change_rate=change_rate
                ))
            except Exception as e:
                logger.warning(f"[WeeklyChangeParser] 행 파싱 실패: {e}")
                continue
                
        return WeeklyChangeReport(
            date=date,
            year=metadata["year"],
            month=metadata["month"],
            week_of_month=metadata["week_of_month"],
            week_num=metadata["week_num"],
            date_range=metadata["date_range"],
            items=items
        )
