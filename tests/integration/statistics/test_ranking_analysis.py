from datetime import datetime, timedelta

import pytest

from evenezer.application.services.statistics_service import StatisticsService
from evenezer.domain.statistics.models import (
    DailyMarketRanking,
    MarketType,
    RankingItem,
    SupplySubject,
)
from evenezer.infrastructure.adapters.local.statistics_repo import LocalStatisticsRepository


@pytest.fixture
def stats_setup(tmp_path):
    """통계 서비스 및 저장소 공통 셋업."""
    repo_dir = tmp_path / "stats"
    repo = LocalStatisticsRepository(data_root=str(repo_dir))
    service = StatisticsService(repository=repo)
    return repo, service

@pytest.mark.asyncio

async def test_ranking_analysis_basic_logic(stats_setup):
    """기본적인 순위 변동 및 연속 등장 로직 검증."""
    repo, service = stats_setup
    market = MarketType.KOSPI
    subject = SupplySubject.FOREIGN

    # Day 1: [A, B, C]
    day1 = DailyMarketRanking(
        date="2026-04-01", market=market, subject=subject,
        items=[RankingItem(rank=i+1, name=f"Stock{chr(65+i)}", amount=100-i) for i in range(3)]
    )
    # Day 2: [A, C, D] (B 탈락, D 신규)
    day2 = DailyMarketRanking(
        date="2026-04-02", market=market, subject=subject,
        items=[
            RankingItem(rank=1, name="StockA", amount=110),
            RankingItem(rank=2, name="StockC", amount=95),
            RankingItem(rank=3, name="StockD", amount=85),
        ]
    )
    service.save_rankings([day1, day2])

    analyzed = await service.get_analyzed_ranking("2026-04-02", market, subject)
    items = {item.name: item for item in analyzed.items}

    assert items["StockA"].rank_change == 0
    assert items["StockA"].consecutive_days == 2
    assert items["StockC"].rank_change == 3 - 2 # 3위 -> 2위 (+1)
    assert items["StockC"].is_new is False
    assert items["StockD"].is_new is True
    assert items["StockD"].consecutive_days == 1

@pytest.mark.asyncio

async def test_ranking_analysis_date_gaps(stats_setup):
    """주말/공휴일 등으로 인한 날짜 간격이 있을 때의 동작 검증."""
    repo, service = stats_setup
    market = MarketType.KOSPI
    subject = SupplySubject.FOREIGN

    # 04-01(금) 데이터
    day1 = DailyMarketRanking(
        date="2026-04-01", market=market, subject=subject,
        items=[RankingItem(rank=1, name="StockA", amount=100)]
    )
    # 04-04(월) 데이터 (사이에 2일 간격)
    day2 = DailyMarketRanking(
        date="2026-04-04", market=market, subject=subject,
        items=[RankingItem(rank=1, name="StockA", amount=110)]
    )
    service.save_rankings([day1, day2])

    analyzed = await service.get_analyzed_ranking("2026-04-04", market, subject)

    # 간격이 있어도 바로 직전 유효 거래일과 비교해야 함
    assert analyzed.previous_date == "2026-04-01"
    assert analyzed.items[0].name == "StockA"
    assert analyzed.items[0].rank_change == 0
    assert analyzed.items[0].consecutive_days == 2

@pytest.mark.asyncio

async def test_ranking_analysis_lookback_limit(stats_setup):
    """탐색 제한(30일) 경계값 테스트."""
    repo, service = stats_setup
    market = MarketType.KOSPI
    subject = SupplySubject.FOREIGN

    # 40일치 연속 데이터 생성
    target_stock = "ConstantStock"
    rankings = []
    base_date = datetime(2026, 1, 1)
    for i in range(40):
        date_str = (base_date + timedelta(days=i)).strftime("%Y-%m-%d")
        rankings.append(DailyMarketRanking(
            date=date_str, market=market, subject=subject,
            items=[RankingItem(rank=1, name=target_stock, amount=1000)]
        ))
    service.save_rankings(rankings)

    # 마지막 날짜 기준 분석
    last_date = rankings[-1].date
    analyzed = await service.get_analyzed_ranking(last_date, market, subject)

    # 연속 등장 횟수가 탐색 제한(10일)까지만 계산되는지 확인
    # (로직상 current_idx + 1에서 시작하여 10일 더 탐색하므로 총 11일까지 나올 수 있음)
    assert analyzed.items[0].name == target_stock
    assert analyzed.items[0].consecutive_days == 11  # 현재(1) + 과거(10)

@pytest.mark.asyncio

async def test_ranking_analysis_boundary_cases(stats_setup):
    """30위권 경계값 및 예외 상황 테스트."""
    repo, service = stats_setup
    market = MarketType.KOSPI
    subject = SupplySubject.FOREIGN

    # Day 1: StockA가 31위 (랭킹 리스트에는 없음)
    day1 = DailyMarketRanking(
        date="2026-04-01", market=market, subject=subject,
        items=[RankingItem(rank=i+1, name=f"Other{i}", amount=100) for i in range(30)]
    )
    # Day 2: StockA가 30위로 진입
    day2 = DailyMarketRanking(
        date="2026-04-02", market=market, subject=subject,
        items=[RankingItem(rank=i+1, name=f"Other{i}", amount=100) for i in range(29)] +
              [RankingItem(rank=30, name="StockA", amount=50)]
    )
    service.save_rankings([day1, day2])

    analyzed = await service.get_analyzed_ranking("2026-04-02", market, subject)
    stock_a = next(item for item in analyzed.items if item.name == "StockA")

    # 이전 랭킹(TOP 30)에 없었으므로 신규 진입으로 간주되어야 함
    assert stock_a.is_new is True
    assert stock_a.prev_rank is None
    assert stock_a.consecutive_days == 1

@pytest.mark.asyncio

async def test_ranking_analysis_empty_repository(stats_setup):
    """저장소가 비어있거나 데이터가 하나뿐인 경우."""
    repo, service = stats_setup
    market = MarketType.KOSPI
    subject = SupplySubject.FOREIGN

    # 데이터가 없을 때
    assert await service.get_analyzed_ranking("2026-04-01", market, subject) is None

    # 데이터가 하나만 있을 때
    day1 = DailyMarketRanking(
        date="2026-04-01", market=market, subject=subject,
        items=[RankingItem(rank=1, name="StockA", amount=100)]
    )
    service.save_rankings([day1])

    analyzed = await service.get_analyzed_ranking("2026-04-01", market, subject)
    assert analyzed.previous_date is None
    assert analyzed.items[0].is_new is True
    assert analyzed.items[0].consecutive_days == 1
