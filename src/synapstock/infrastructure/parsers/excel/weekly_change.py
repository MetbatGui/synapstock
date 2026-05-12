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

    def parse(self, content: bytes, **kwargs) -> WeeklyChangeReport:
        """엑셀 내용을 파싱하여 WeeklyChangeReport를 반환합니다.
        
        Args:
            content: 엑셀 파일 바이너리.
            filename: 파일 이름 (메타데이터 추출용).
            date: 기준 일자 (명시적으로 주어질 경우 우선함).
        """
        filename = kwargs.get("filename", "")
        metadata = self.extract_metadata_from_filename(filename)
        
        # 명시적인 date가 인자로 오면 그것을 우선함
        date = kwargs.get("date") or metadata["date"]
        
        df = pd.read_excel(io.BytesIO(content))
        
        items = []
        for _, row in df.iterrows():
            try:
                name = self._clean_stock_name(str(row.get("종목명", row.iloc[0])))
                if not name or name == "nan":
                    continue
                    
                current_price = self.to_int(row.get("현재가", 0))
                prev_week_close = self.to_int(row.get("전주종가", 0))
                change_rate = self.to_float(row.get("등락률", 0.0))
                
                items.append(WeeklyChangeItem(
                    name=name,
                    current_price=current_price,
                    prev_week_close=prev_week_close,
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
