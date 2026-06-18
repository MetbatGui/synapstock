import logging
import threading
from datetime import datetime, timedelta

from evenezer.domain.ports import KrxDataPort

logger = logging.getLogger(__name__)

# 전역 공유 캐시 변수 (10분 인메모리 list[dict]) 및 동시성 락
_global_cache_list: list[dict] | None = None
_global_cache_expired_at: datetime | None = None
_global_cache_lock = threading.Lock()


def get_shared_cache(now: datetime) -> list[dict] | None:
    """공유 인메모리 캐시를 획득합니다. 캐시 만료 시 자원을 명시적으로 해제합니다.

    주의: 이 함수는 호출자가 락을 획득했는지와 관계없이 빠르게 읽기 전용으로 대조할 수 있습니다.
    """
    global _global_cache_list, _global_cache_expired_at
    if _global_cache_list is not None and _global_cache_expired_at is not None:
        if now < _global_cache_expired_at:
            return _global_cache_list
        else:
            # 캐시 만료 시 자원 명시 해제
            _global_cache_list = None
            _global_cache_expired_at = None
    return None


class CachingKrxRepository(KrxDataPort):
    """KrxDataPort 데코레이터로, 10분 동안 조회 결과를 인메모리에 캐싱합니다.

    Double-checked Locking 기법을 적용하여 Cache Stampede를 방지합니다.
    """

    def __init__(self, delegate: KrxDataPort):
        self._delegate = delegate

    def fetch_net_purchase_data(self, market: str, investor: str, date_str: str) -> bytes:
        return self._delegate.fetch_net_purchase_data(market, investor, date_str)

    def fetch_market_prices(self, market: str, date_str: str) -> list[dict]:
        return self._delegate.fetch_market_prices(market, date_str)

    def fetch_listing(self, date: datetime | None = None) -> list[dict]:
        now = datetime.now()
        if date is None:
            # 1. 락 없이 빠른 캐시 체크
            cached_list = get_shared_cache(now)
            if cached_list is not None:
                logger.info("KRX 전종목 시세 10분 캐시 히트 (유효 - CachingKrxRepository)")
                return cached_list

        # 2. 락 획득 후 임계 구역 진입
        with _global_cache_lock:
            if date is None:
                # Double check
                cached_list = get_shared_cache(now)
                if cached_list is not None:
                    logger.info("KRX 전종목 시세 10분 캐시 히트 (대기 후 히트 - CachingKrxRepository)")
                    return cached_list

            raw_list = self._delegate.fetch_listing(date)

            if date is None and raw_list:
                global _global_cache_list, _global_cache_expired_at
                _global_cache_list = raw_list
                _global_cache_expired_at = now + timedelta(minutes=10)
                logger.info("KRX 전종목 시세 신규 수집 및 10분 캐싱 완료 (CachingKrxRepository)")

            return raw_list
