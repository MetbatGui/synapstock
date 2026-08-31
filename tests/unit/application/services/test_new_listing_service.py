"""NewListingService 유닛 테스트 (TDD: 구현보다 먼저 작성).

repository는 실제 LocalStatisticsRepository의 save_new_listings(items, year)/
get_new_listings(year) 시그니처를 그대로 따르는 스텁을 쓴다 - MagicMock의
"아무 메서드나 자동 통과" 함정을 피하기 위해 필요한 메서드만 명시적으로 스텁한다.
"""
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from evenezer.application.services.new_listing_service import NewListingService

COLUMNS = ["종목명", "시장구분", "상장일", "확정공모가", "액면가", "기관경쟁률", "유통가능물량(%)"]


def make_stocks_db(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    col_list = ",".join(f'"{c}"' for c in COLUMNS)
    conn.execute(f"CREATE TABLE stocks ({col_list})")
    placeholders = ",".join("?" for _ in COLUMNS)
    for row in rows:
        conn.execute(f"INSERT INTO stocks VALUES ({placeholders})", [row.get(c) for c in COLUMNS])
    conn.commit()
    conn.close()


class FakeRepository:
    """LocalStatisticsRepository의 new_listing 관련 메서드만 명시적으로 흉내낸다."""

    def __init__(self):
        self.saved: dict[str, list] = {}

    def save_new_listings(self, items, year="2026"):
        self.saved[year] = items

    def get_new_listings(self, year="2026") -> list:
        return self.saved.get(year, [])


@pytest.fixture
def repo():
    return FakeRepository()


@pytest.fixture
def db_sync_stub(tmp_path):
    paths: dict[int, Path] = {}

    def register(year: int, rows: list[dict]):
        p = tmp_path / f"{year}.db"
        make_stocks_db(p, rows)
        paths[year] = p

    async def ensure_db(year, force=False):
        return paths.get(year)

    stub = MagicMock()
    stub.ensure_db = AsyncMock(side_effect=ensure_db)
    stub.register = register
    return stub


@pytest.fixture
def service(repo, db_sync_stub):
    drive = MagicMock()
    return NewListingService(drive, "new_listing", repo, db_sync=db_sync_stub)


@pytest.mark.asyncio
async def test_sync_data_no_drive_adapter_returns_empty(repo, db_sync_stub):
    service = NewListingService(None, "new_listing", repo, db_sync=db_sync_stub)
    assert await service.sync_data("2026") == []
    db_sync_stub.ensure_db.assert_not_called()


@pytest.mark.asyncio
async def test_sync_data_no_remote_db_returns_empty(service):
    assert await service.sync_data("2026") == []


@pytest.mark.asyncio
async def test_sync_data_maps_fields_and_saves_to_repository(service, repo, db_sync_stub):
    db_sync_stub.register(
        2026,
        rows=[
            {"종목명": "삼성전자", "시장구분": "코스피", "상장일": "2026-01-15",
             "확정공모가": 70000, "액면가": 100},
        ],
    )

    result = await service.sync_data("2026")

    assert len(result) == 1
    listing = result[0]
    assert listing.name == "삼성전자"
    assert listing.market == "코스피"
    assert listing.listing_date == "2026-01-15"
    assert listing.offer_price == 70000
    assert listing.face_value == 100
    assert repo.saved["2026"] == result


@pytest.mark.asyncio
async def test_sync_data_missing_optional_fields_default_safely(service, db_sync_stub):
    """생산자 DB에 없는 컬럼(예: 이 fixture엔 없는 필드)은 기본값으로 안전하게 채워야 한다."""
    db_sync_stub.register(2026, rows=[{"종목명": "삼성전자", "상장일": "2026-01-15"}])

    result = await service.sync_data("2026")

    listing = result[0]
    assert listing.offer_price == 0
    assert listing.ticker is None


@pytest.mark.asyncio
async def test_sync_data_parses_ratio_and_percent_text_columns(service, db_sync_stub):
    """실 Drive 데이터로 확인함: 기관경쟁률은 "650:1", 유통가능물량(%)은 "32.33%"처럼
    원본 텍스트 형식 그대로 저장돼 있다 - 단순 float() 캐스팅은 여기서 터진다."""
    db_sync_stub.register(
        2026,
        rows=[
            {"종목명": "덕양에너젠", "상장일": "2026.01.30",
             "기관경쟁률": "650:1", "유통가능물량(%)": "32.33%"},
        ],
    )

    result = await service.sync_data("2026")

    listing = result[0]
    assert listing.listing_date == "2026.01.30"
    assert listing.institutional_competition == 650.0
    assert listing.float_shares_pct == 32.33


@pytest.mark.asyncio
async def test_get_data_uses_local_cache_when_available(service, repo, db_sync_stub):
    repo.saved["2026"] = ["cached_sentinel"]

    result = await service.get_data("2026")

    assert result == ["cached_sentinel"]
    db_sync_stub.ensure_db.assert_not_called()


@pytest.mark.asyncio
async def test_get_data_force_sync_bypasses_local_cache(service, repo, db_sync_stub):
    repo.saved["2026"] = ["cached_sentinel"]
    db_sync_stub.register(2026, rows=[{"종목명": "삼성전자", "상장일": "2026-01-15"}])

    result = await service.get_data("2026", force_sync=True)

    assert result != ["cached_sentinel"]
    db_sync_stub.ensure_db.assert_called_once_with(2026, force=True)
