import pytest
from synapstock.domain.statistics.models import (
    DailyMarketRanking,
    RankingItem,
    MarketType,
    SupplySubject,
    MonthlyMarketStats
)

def test_monthly_market_stats_aggregation():
    """여러 일별 랭킹 데이터를 합산하여 월간 통계를 생성하는 로직 테스트"""
    
    # 1. 테스트 데이터 준비 (2일치 데이터)
    day1_items = [
        RankingItem(rank=1, name="삼성전자", amount=1000, ticker="005930"),
        RankingItem(rank=2, name="SK하이닉스", amount=500, ticker="000660"),
    ]
    day2_items = [
        RankingItem(rank=1, name="삼성전자", amount=2000, ticker="005930"),
        RankingItem(rank=2, name="현대차", amount=800, ticker="005380"),
    ]
    
    day1 = DailyMarketRanking(
        date="2024-04-01", 
        market=MarketType.KOSPI, 
        subject=SupplySubject.FOREIGN, 
        items=day1_items
    )
    day2 = DailyMarketRanking(
        date="2024-04-02", 
        market=MarketType.KOSPI, 
        subject=SupplySubject.FOREIGN, 
        items=day2_items
    )
    
    # 2. 합산 로직 실행 (아직 구현되지 않은 클래스 메서드 호출 가정)
    # 실제 구현 시 MonthlyMarketStats.aggregate_from_daily(month, rankings) 형태가 될 것임
    monthly_stats = MonthlyMarketStats.aggregate_from_daily(
        month="2024-04",
        rankings=[day1, day2]
    )
    
    # 3. 결과 검증
    assert monthly_stats.month == "2024-04"
    assert monthly_stats.market == MarketType.KOSPI
    assert monthly_stats.subject == SupplySubject.FOREIGN
    
    # 순위 순서: 삼성전자(3000) > 현대차(800) > SK하이닉스(500)
    assert len(monthly_stats.items) == 3
    assert monthly_stats.items[0].name == "삼성전자"
    assert monthly_stats.items[0].amount == 3000
    assert monthly_stats.items[1].name == "현대차"
    assert monthly_stats.items[1].amount == 800
    assert monthly_stats.items[2].name == "SK하이닉스"
    assert monthly_stats.items[2].amount == 500
    
    # 순위(rank) 값도 올바르게 설정되었는지 확인
    assert monthly_stats.items[0].rank == 1
    assert monthly_stats.items[1].rank == 2
    assert monthly_stats.items[2].rank == 3
