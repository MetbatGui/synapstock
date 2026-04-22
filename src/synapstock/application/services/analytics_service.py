import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class AnalyticsService:
    def __init__(self, market_data_repo: Any):
        self._repo = market_data_repo

    def _get_past_trading_days(self, target_date: str, days: int = 20) -> list[str]:
        """target_date를 포함하여 역순으로 과거 N개의 거래일 반환"""
        base_dir = self._repo.base_dir
        # 디렉토리명(날짜) 목록 확보
        all_dirs = []
        if os.path.exists(base_dir):
            for d in os.listdir(base_dir):
                if d.startswith("20") and len(d) == 8:
                    all_dirs.append(d)

        all_dirs.sort(reverse=True)  # 내림차순 정렬 (최신순)

        past_days = []
        for d in all_dirs:
            if d <= target_date:
                # 거래일 확인 (STK 가격 파일 존재 여부 기준)
                if self._repo.exists(d, "prices_STK"):
                    past_days.append(d)
                    if len(past_days) >= days:
                        break
        return past_days

    # [compute_z_ofi_for_tickers 제거됨]
