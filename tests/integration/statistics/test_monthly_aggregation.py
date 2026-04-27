from unittest.mock import MagicMock

import pytest

from synapstock.application.services.query_service import BoardQueryService
from synapstock.application.services.statistics_service import StatisticsService
from synapstock.domain.statistics.models import (
    DailyMarketRanking,
    MarketType,
    RankingItem,
    SupplySubject,
)
from synapstock.infrastructure.adapters.local.statistics_repo import LocalStatisticsRepository


@pytest.fixture
def monthly_stats_setup(tmp_path):
    """월간 통계 테스트를 위한 서비스 및 종속성 셋업."""
    repo_dir = tmp_path / "stats"
    repo = LocalStatisticsRepository(data_root=str(repo_dir))

    # QueryService 모킹 (로컬 티커 맵 빌드 테스트용)
    mock_query_service = MagicMock(spec=BoardQueryService)

    # 보드에 등록된 샘플 종목 데이터 설정
    mock_query_service.get_all_stocks_flat.return_value = [
        {"name": "삼성전자", "ticker": "005930"},
        {"name": "SK하이닉스", "ticker": "000660"},
        {"name": "카카오", "ticker": "035720"}
    ]

    service = StatisticsService(repository=repo, query_service=mock_query_service)
    return repo, service, mock_query_service

@pytest.mark.asyncio

async def test_monthly_aggregation_accumulation(monthly_stats_setup):
    """여러 날짜의 데이터가 올바르게 합산되는지 검증."""
    repo, service, _ = monthly_stats_setup
    market = MarketType.KOSPI
    subject = SupplySubject.FOREIGN

    # 2026-04-01: 삼성전자 100, SK하이닉스 50
    day1 = DailyMarketRanking(
        date="2026-04-01", market=market, subject=subject,
        items=[
            RankingItem(rank=1, name="삼성전자", amount=100),
            RankingItem(rank=2, name="SK하이닉스", amount=50)
        ]
    )
    # 2026-04-02: 삼성전자 200, 카카오 150
    day2 = DailyMarketRanking(
        date="2026-04-02", market=market, subject=subject,
        items=[
            RankingItem(rank=1, name="삼성전자", amount=200),
            RankingItem(rank=2, name="카카오", amount=150)
        ]
    )
    service.save_rankings([day1, day2])

    # 4월 월간 집계 수행
    result = await service.get_monthly_ranking("2026-04", market, subject)

    assert result.month == "2026-04"
    items = {item.name: item.amount for item in result.items}

    # 합산 결과 확인
    assert items["삼성전자"] == 300
    assert items["SK하이닉스"] == 50
    assert items["카카오"] == 150

    # 상위 종목 순 정렬 확인
    assert result.items[0].name == "삼성전자"
    assert result.items[1].name == "카카오"
    assert result.items[2].name == "SK하이닉스"

@pytest.mark.asyncio

async def test_monthly_aggregation_ticker_mapping(monthly_stats_setup):
    """로컬 보드 데이터를 활용한 티커 매핑 최적화 로직 검증."""
    repo, service, mock_query_service = monthly_stats_setup
    market = MarketType.KOSPI
    subject = SupplySubject.FOREIGN

    day = DailyMarketRanking(
        date="2026-04-01", market=market, subject=subject,
        items=[
            RankingItem(rank=1, name="삼성전자", amount=100),
            RankingItem(rank=2, name="미등록종목", amount=50) # 보드(Mock)에 없는 종목
        ]
    )
    service.save_rankings([day])

    result = await service.get_monthly_ranking("2026-04", market, subject)

    items = {item.name: item for item in result.items}

    # 보드에 있는 종목은 티커가 매핑되어야 함
    assert items["삼성전자"].ticker == "005930"

    # 보드에 없는 종목은 티커가 None이어야 함 (최적화 로직에 의해 외부 API 호출 안 함)
    assert items["미등록종목"].ticker is None

    # QueryService의 get_all_stocks_flat이 한 번만 호출되었는지 확인 (최적화 확인)
    assert mock_query_service.get_all_stocks_flat.call_count == 1
    # 개별 종목 검색 API(search_ticker)는 호출되지 않아야 함
    assert mock_query_service.search_ticker.call_count == 0

@pytest.mark.asyncio

async def test_monthly_aggregation_empty_data(monthly_stats_setup):
    """데이터가 없는 월에 대한 처리 검증."""
    _, service, _ = monthly_stats_setup

    result = await service.get_monthly_ranking("2099-12", MarketType.KOSPI, SupplySubject.FOREIGN)

    assert result.items == []
    assert result.month == "2099-12"

@pytest.mark.asyncio

async def test_monthly_aggregation_sorting_and_limit(monthly_stats_setup):
    """매우 많은 종목이 있을 때 상위 30개까지만 정렬되어 반환되는지 확인."""
    repo, service, _ = monthly_stats_setup
    market = MarketType.KOSPI
    subject = SupplySubject.FOREIGN

    # 50개의 종목 데이터 생성
    items = [RankingItem(rank=i+1, name=f"Stock{i:02d}", amount=500-i) for i in range(50)]
    day = DailyMarketRanking(date="2026-04-01", market=market, subject=subject, items=items)
    service.save_rankings([day])

    result = await service.get_monthly_ranking("2026-04", market, subject)

    assert len(result.items) == 30
    assert result.items[0].name == "Stock00"
    assert result.items[0].amount == 500
    assert result.items[29].name == "Stock29"
    assert result.items[29].amount == 500-29
