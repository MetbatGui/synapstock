"""RankingService.sync_data() 유닛 테스트.

netbuy DB SSOT 구독으로 전환한 뒤의 공개 계약(sync_data/get_daily_ranking)을
검증한다. DB 동기화(db_sync)와 쿼리(netbuy_db_query)는 fixture DB로 실제
SQLite를 써서 검증한다 - mock이 아니라 진짜 SQLite여야 SQL 오류를 여기서 잡는다.
"""
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from evenezer.application.services.ranking_service import RankingService
from evenezer.domain.statistics.models import MarketType, SupplySubject


def make_market_data_db(path: Path, netbuy_rows: list[tuple]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE netbuy (date_str TEXT, market TEXT, investor TEXT, rank INTEGER, "
        "stock_code TEXT, stock_name TEXT, net_buy_amount INTEGER, "
        "PRIMARY KEY (date_str, market, investor, rank))"
    )
    conn.execute(
        "CREATE TABLE price_info (date_str TEXT, stock_code TEXT, stock_name TEXT, "
        "close_price REAL, high_52w REAL, all_time_high REAL, "
        "PRIMARY KEY (date_str, stock_code))"
    )
    conn.executemany("INSERT INTO netbuy VALUES (?,?,?,?,?,?,?)", netbuy_rows)
    conn.commit()
    conn.close()


@pytest.fixture
def mock_repo():
    repo = MagicMock()
    repo.list_available_dates.return_value = []
    repo.get_rankings.return_value = []
    return repo


@pytest.fixture
def db_sync_stub(tmp_path):
    """연도별로 등록된 fixture market_data_{year}.db 경로만 반환하는 스텁."""
    paths: dict[int, Path] = {}

    def register(year: int, netbuy_rows: list[tuple]):
        p = tmp_path / f"market_data_{year}.db"
        make_market_data_db(p, netbuy_rows)
        paths[year] = p

    async def ensure_db(year, force=False):
        return paths.get(year)

    stub = MagicMock()
    stub.ensure_db = AsyncMock(side_effect=ensure_db)
    stub.register = register
    return stub


@pytest.fixture
def service(mock_repo, db_sync_stub):
    drive = MagicMock()
    return RankingService(drive, "sd", mock_repo, db_sync=db_sync_stub)


@pytest.mark.asyncio
async def test_sync_data_no_drive_adapter_returns_empty(mock_repo, db_sync_stub):
    service = RankingService(None, "sd", mock_repo, db_sync=db_sync_stub)
    assert await service.sync_data("2026-08-28") == []
    db_sync_stub.ensure_db.assert_not_called()


@pytest.mark.asyncio
async def test_sync_data_no_remote_db_falls_back_to_local(service, mock_repo):
    mock_repo.get_rankings.return_value = ["cached"]
    mock_repo.list_available_dates.return_value = ["2026-08-20"]

    result = await service.sync_data("2026-08-28")

    assert result == ["cached"]


@pytest.mark.asyncio
async def test_sync_data_uses_year_from_date_str(service, db_sync_stub):
    db_sync_stub.register(2025, [])

    await service.sync_data("2025-12-30")

    db_sync_stub.ensure_db.assert_called_once_with(2025)


@pytest.mark.asyncio
async def test_sync_data_skips_dates_already_in_local_repository(service, mock_repo, db_sync_stub):
    """기존 로컬에 있는 날짜(KOSPI/FOREIGN 대표값)는 재조립하지 않는다."""
    mock_repo.list_available_dates.return_value = ["2026-08-27"]
    db_sync_stub.register(
        2026,
        [
            ("20260827", "KOSPI", "foreigner", 1, "005930", "삼성전자", 1000),
            ("20260828", "KOSPI", "foreigner", 1, "005930", "삼성전자", 1200),
        ],
    )

    result = await service.sync_data(None)

    dates_synced = {r.date for r in result}
    assert dates_synced == {"2026-08-28"}


@pytest.mark.asyncio
async def test_sync_data_builds_all_four_combos_and_saves_to_repository(service, mock_repo, db_sync_stub):
    db_sync_stub.register(
        2026,
        [
            ("20260828", "KOSPI", "foreigner", 1, "005930", "삼성전자", 1000),
            ("20260828", "KOSPI", "institutions", 1, "005380", "현대차", 500),
            ("20260828", "KOSDAQ", "foreigner", 1, "086520", "에코프로", 300),
            ("20260828", "KOSDAQ", "institutions", 1, "247540", "에코프로비엠", 200),
        ],
    )

    result = await service.sync_data(None)

    combos = {(r.market, r.subject) for r in result}
    assert combos == {
        (MarketType.KOSPI, SupplySubject.FOREIGN),
        (MarketType.KOSPI, SupplySubject.INSTITUTION),
        (MarketType.KOSDAQ, SupplySubject.FOREIGN),
        (MarketType.KOSDAQ, SupplySubject.INSTITUTION),
    }
    assert mock_repo.save_daily_ranking.call_count == 4


@pytest.mark.asyncio
async def test_sync_data_maps_ticker_and_high_price_type(service, mock_repo, db_sync_stub):
    db_sync_stub.register(
        2026, [("20260828", "KOSPI", "foreigner", 1, "005930", "삼성전자", 1000)]
    )

    result = await service.sync_data(None)

    kospi_foreign = next(r for r in result if r.market == MarketType.KOSPI and r.subject == SupplySubject.FOREIGN)
    item = kospi_foreign.items[0]
    assert item.ticker == "005930"
    assert item.name == "삼성전자"
    assert item.amount == 1000
    assert item.high_price_type is None  # price_info 없음
