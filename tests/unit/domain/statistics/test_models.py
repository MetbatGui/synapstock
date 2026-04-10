from synapstock.domain.statistics import MarketType, SupplySubject, RankingItem, DailyMarketRanking
import pytest

def test_create_daily_market_ranking():
    """DailyMarketRanking 모델 생성 및 데이터 검증 테스트."""
    item = RankingItem(rank=1, name="삼성전자", amount=1234567, ticker="005930")
    
    ranking = DailyMarketRanking(
        date="2024-04-06",
        market=MarketType.KOSPI,
        subject=SupplySubject.FOREIGN,
        items=[item]
    )
    
    assert ranking.date == "2024-04-06"
    assert ranking.market == "KOSPI"
    assert ranking.subject == "FOREIGN"
    assert len(ranking.items) == 1
    assert ranking.items[0].name == "삼성전자"
    assert ranking.items[0].ticker == "005930"

def test_market_type_enum():
    """MarketType Enum 값이 올바른지 확인."""
    assert MarketType.KOSPI == "KOSPI"
    assert MarketType.KOSDAQ == "KOSDAQ"

def test_supply_subject_enum():
    """SupplySubject Enum 값이 올바른지 확인."""
    assert SupplySubject.FOREIGN == "FOREIGN"
    assert SupplySubject.INSTITUTION == "INSTITUTION"
