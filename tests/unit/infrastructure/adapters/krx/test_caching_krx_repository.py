import pytest
from datetime import datetime
from evenezer.domain.ports import KrxDataPort
from evenezer.infrastructure.adapters.heatmap.caching_krx_repository import CachingKrxRepository


class DummyKrxAdapter(KrxDataPort):
    """NativeKrxAdapter처럼 Name 컬럼 없이 ISU_ABBRV 구조를 리턴하는 더미"""
    def fetch_net_purchase_data(self, market: str, investor: str, date_str: str) -> bytes:
        return b""

    def fetch_market_prices(self, market: str, date_str: str) -> list[dict]:
        return []

    def fetch_listing(self, date: datetime | None = None) -> list[dict]:
        return [{"Code": "005930", "ISU_ABBRV": "삼성전자"}]


class DummyKrxRepository(KrxDataPort):
    """KrxRepository처럼 Name 컬럼을 포함하여 정형화된 구조를 리턴하는 더미"""
    def fetch_net_purchase_data(self, market: str, investor: str, date_str: str) -> bytes:
        return b""

    def fetch_market_prices(self, market: str, date_str: str) -> list[dict]:
        return []

    def fetch_listing(self, date: datetime | None = None) -> list[dict]:
        return [{"Code": "005930", "Name": "삼성전자"}]


def test_caching_krx_repository_isolation():
    """서로 다른 어댑터를 감싼 CachingKrxRepository 인스턴스 간에 캐시가 오염 및 공유되지 않는지 검증합니다."""
    # 1. 2개의 어댑터 인스턴스 및 각각 캐시 레포 생성
    adapter_dummy = DummyKrxAdapter()
    repo_dummy = DummyKrxRepository()

    caching_adapter = CachingKrxRepository(adapter_dummy)
    caching_repo = CachingKrxRepository(repo_dummy)

    # 2. 1번째 레포(Name 없는 데이터) fetch_listing 실행 -> 캐시 적재
    data_adapter = caching_adapter.fetch_listing()
    assert "ISU_ABBRV" in data_adapter[0]
    assert "Name" not in data_adapter[0]

    # 3. 2번째 레포(Name 있는 데이터) fetch_listing 실행
    data_repo = caching_repo.fetch_listing()
    
    # 4. 캐시 격리 검증: 2번째 레포가 1번째 레포의 캐시(Name 없음)로 오염되지 않고 자신의 온전한 데이터를 가져와야 함
    assert "Name" in data_repo[0]
    assert "ISU_ABBRV" not in data_repo[0]
    assert data_repo[0]["Name"] == "삼성전자"
