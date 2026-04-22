import logging
import re
from abc import ABC, abstractmethod
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


class BaseExcelParser(ABC):
    """모든 엑셀 통계 파서의 기반이 되는 추상 클래스.
    공통 유틸리티 메서드와 인터페이스를 정의합니다.
    """

    @abstractmethod
    def parse(self, content: bytes, **kwargs) -> Any:
        """바이너리 엑셀 데이터를 도메인 모델로 파싱합니다."""
        pass

    @staticmethod
    def _clean_stock_name(name: str) -> str:
        """종목명에서 '(쌍)', '(씽)', '(상)' 등의 노이즈 문자를 제거합니다."""
        name_str = str(name).strip()
        # 종목명 뒤에 공백과 함께 (쌍), (씽), (상) 등이 괄호로 붙은 경우 제거
        cleaned = re.sub(r"\s*\([쌍씽상]\)$", "", name_str)
        return cleaned.strip()

    @staticmethod
    def to_int(val: Any) -> int:
        """다양한 형식의 데이터를 정수로 안전하게 변환합니다."""
        if pd.isna(val) or val == "" or val == "-":
            return 0
        if isinstance(val, (int, float)):
            return int(val)
        cleaned = re.sub(r"[^0-9-]", "", str(val))
        return int(cleaned) if cleaned else 0

    @staticmethod
    def to_float(val: Any) -> float:
        """다양한 형식의 데이터를 실수로 안전하게 변환합니다. '650:1'과 같은 경쟁률 형식도 처리합니다."""
        if pd.isna(val) or val == "" or val == "-":
            return 0.0
        if isinstance(val, (int, float)):
            return float(val)

        val_str = str(val).strip()
        # '650:1' 같은 경쟁률 형식에서 앞의 숫자만 추출
        if ":" in val_str:
            val_str = val_str.split(":")[0]

        cleaned = re.sub(r"[^0-9.-]", "", val_str)
        return float(cleaned) if cleaned else 0.0

    @staticmethod
    def to_str(val: Any) -> str:
        """데이터를 문자열로 정제하여 반환합니다. 날짜 형식 포함."""
        if pd.isna(val):
            return ""
        if isinstance(val, pd.Timestamp):
            return val.strftime("%Y-%m-%d")
        return str(val).strip()

    @staticmethod
    def get_val(row: pd.Series, *keys: str) -> Any:
        """여러 개의 가능한 키 중 가장 먼저 매칭되는 컬럼의 값을 반환합니다. (유연한 헤더 매칭)"""
        for key in keys:
            cleaned_key = re.sub(r"\s+", "", key)
            for col in row.index:
                cleaned_col = re.sub(r"\s+", "", str(col))
                if cleaned_key in cleaned_col:
                    return row.get(col)
        return None

    @staticmethod
    def _format_date(yymmdd: str) -> str:
        """YYMMDD 또는 YYYYMMDD 형태의 날짜를 YYYY-MM-DD 형식으로 변환합니다."""
        if not yymmdd:
            return ""

        cleaned = re.sub(r"[^0-9]", "", str(yymmdd))
        if len(cleaned) == 8:
            return f"{cleaned[:4]}-{cleaned[4:6]}-{cleaned[6:]}"
        elif len(cleaned) == 6:
            prefix = "20"  # 기본적으로 2000년대 가정
            return f"{prefix}{cleaned[:2]}-{cleaned[2:4]}-{cleaned[4:]}"
        return cleaned
