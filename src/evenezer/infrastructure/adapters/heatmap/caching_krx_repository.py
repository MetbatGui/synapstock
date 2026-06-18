import logging
from datetime import datetime, timedelta

import pandas as pd

from evenezer.domain.heatmap.ports import KrxDataPort as HeatmapKrxDataPort
from evenezer.domain.ports import KrxDataPort as DomainKrxDataPort

logger = logging.getLogger(__name__)

# 전역 공유 캐시 변수 (10분 인메모리)
_global_cache_df: pd.DataFrame | None = None
_global_cache_expired_at: datetime | None = None


def get_shared_cache(now: datetime) -> pd.DataFrame | None:
    """공유 인메모리 캐시를 획득합니다."""
    global _global_cache_df, _global_cache_expired_at
    if _global_cache_df is not None and _global_cache_expired_at is not None:
        if now < _global_cache_expired_at:
            return _global_cache_df
    return None


def set_shared_cache(df: pd.DataFrame, expired_at: datetime):
    """공유 인메모리 캐시를 갱신합니다."""
    global _global_cache_df, _global_cache_expired_at
    _global_cache_df = df
    _global_cache_expired_at = expired_at


class CachingKrxRepository(HeatmapKrxDataPort):
    """HeatmapKrxDataPort 데코레이터로, 10분 동안 조회 결과를 인메모리에 캐싱합니다.
    공유 캐시 스토어를 사용하여 타 영역과 캐시를 통합 관리합니다.
    """

    def __init__(self, delegate: HeatmapKrxDataPort):
        self._delegate = delegate

    def fetch_listing(self, date: datetime | None = None) -> pd.DataFrame:
        """10분 인메모리 캐싱 정책을 적용하여 KRX 상장 종목 데이터를 조회합니다.

        조회 날짜가 None(오늘 실시간)일 때만 캐싱이 적용됩니다.
        """
        now = datetime.now()
        if date is None:
            cached_df = get_shared_cache(now)
            if cached_df is not None:
                logger.info("KRX 전종목 시세 10분 캐시 히트 (유효 - CachingKrxRepository)")
                return cached_df

        df_result = self._delegate.fetch_listing(date)

        if date is None and not df_result.empty:
            set_shared_cache(df_result, now + timedelta(minutes=10))
            logger.info("KRX 전종목 시세 신규 수집 및 10분 캐싱 완료 (CachingKrxRepository)")

        return df_result


class CachingNativeKrxAdapter(DomainKrxDataPort):
    """DomainKrxDataPort 데코레이터로, 10분 동안 조회 결과를 인메모리에 캐싱합니다.
    공유 캐시 스토어를 사용하여 HeatmapKrxDataPort 캐시와 통합 관리합니다.
    """

    def __init__(self, delegate: DomainKrxDataPort):
        self._delegate = delegate

    def fetch_net_purchase_data(self, market: str, investor: str, date_str: str) -> bytes:
        """KrxDataPort의 추상 메소드 위임"""
        return self._delegate.fetch_net_purchase_data(market, investor, date_str)

    def fetch_market_prices(self, market: str, date_str: str) -> list[dict]:
        """KrxDataPort의 추상 메소드 위임"""
        return self._delegate.fetch_market_prices(market, date_str)

    def fetch_listing(self, date: datetime | None = None) -> list[dict]:
        """10분 인메모리 캐싱 정책을 적용하여 KRX 상장 종목 데이터를 조회합니다.

        조회 날짜가 None(오늘 실시간)일 때만 캐싱이 적용됩니다.
        """
        now = datetime.now()
        if date is None:
            cached_df = get_shared_cache(now)
            if cached_df is not None:
                logger.info("KRX 전종목 시세 10분 캐시 히트 (유효 - CachingNativeKrxAdapter)")
                return self._df_to_list_of_dict(cached_df)

        raw_list = self._delegate.fetch_listing(date)

        if date is None and raw_list:
            df_result = pd.DataFrame(raw_list)
            set_shared_cache(df_result, now + timedelta(minutes=10))
            logger.info("KRX 전종목 시세 신규 수집 및 10분 캐싱 완료 (CachingNativeKrxAdapter)")

        return raw_list

    def _df_to_list_of_dict(self, df: pd.DataFrame) -> list[dict]:
        """pd.DataFrame의 컬럼 구성을 list[dict] 형태의 표준 스키마로 가공합니다."""
        records = []
        for _, row in df.iterrows():
            records.append({
                "Code": row.get("Code", ""),
                "Name": row.get("Name", ""),
                "Marcap": row.get("Marcap", 0.0),
                "ChagesRatio": row.get("ChagesRatio", 0.0),
                "Close": row.get("Close", 0),
            })
        return records
