import pytest
import os
import glob
from synapstock.application.services.statistics_service import ExcelStatisticsParser
from synapstock.domain.statistics.models import MarketType, SupplySubject

def test_clean_stock_name():
    """종목명 정제 로직 테스트 ((쌍), (씽), (상) 등 제거 확인)"""
    parser = ExcelStatisticsParser()
    assert parser._clean_stock_name("삼성전자") == "삼성전자"
    assert parser._clean_stock_name("삼성전자 (쌍)") == "삼성전자"
    assert parser._clean_stock_name("SK하이닉스(씽)") == "SK하이닉스"
    assert parser._clean_stock_name("LG에너지솔루션 (상)") == "LG에너지솔루션"
    assert parser._clean_stock_name("  현대차 (쌍)  ") == "현대차"
    assert parser._clean_stock_name("정상종목 (우)") == "정상종목 (우)" # 우 우선주는 제거하면 안됨

def test_parse_real_daily_ranking():
    """테스트 픽스처의 일별 수급 엑셀 파일 파싱 테스트."""
    # 고정된 테스트용 픽스처 경로 사용
    file_path = os.path.join("tests", "fixtures", "statistics", "daily_ranking_20260407.xlsx")
    
    if not os.path.exists(file_path):
        pytest.skip(f"픽스처 파일이 존재하지 않습니다: {file_path}")
        
    with open(file_path, "rb") as f:
        content = f.read()
        
    parser = ExcelStatisticsParser()
    # 0407 시트 파싱 (종합 순위표 형식)
    rankings = parser.parse_summary_table(
        content=content,
        sheet_name="0407",
        date="2026-04-07"
    )
    
    assert len(rankings) == 4  # KOSPI F/I, KOSDAQ F/I
    kospi_for = next(r for r in rankings if r.market == MarketType.KOSPI and r.subject == SupplySubject.FOREIGN)
    
    assert kospi_for.items[0].name == "SK하이닉스"
    assert kospi_for.items[0].amount == 532352
    
    # 엑셀 분석 결과 상위 종목 확인 (삼성전자, SK하이닉스 등)
    first_item = kospi_for.items[0]
    assert first_item.rank == 1
    assert first_item.amount >= 0
    print(f"\n[Parsed Top 10] {file_path}")
    for item in kospi_for.items[:10]:
        print(f"Rank {item.rank}: {item.name} ({item.amount})")

def test_parse_real_monthly_cumulative():
    """월간 누적 엑셀 파일 파싱 테스트."""
    parser = ExcelStatisticsParser()
    
    # 1. 테스트용 더미 엑셀 파일 생성
    import io
    import pandas as pd
    
    data = [
        ["종목명", "순매수금액"],
        ["삼성전자 (쌍)", 1000000],
        ["SK하이닉스 (씽)", 500000],
        ["LG에너지솔루션", 300000],
    ]
    df = pd.DataFrame(data)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='APR', index=False, header=False)
    
    content = output.getvalue()
    
    # 2. 파싱 수행
    stats = parser.parse_monthly_stats(
        content=content,
        market=MarketType.KOSPI,
        subject=SupplySubject.FOREIGN,
        month="202604"
    )
    
    # 3. 검증
    assert stats.month == "202604"
    assert len(stats.items) == 3
    assert stats.items[0].name == "삼성전자"
    assert stats.items[0].amount == 1000000
    assert stats.items[0].rank == 1
    assert stats.items[2].name == "LG에너지솔루션"

def test_statistics_service_caching(tmp_path):
    """StatisticsService의 저장소 연독 및 캐싱 기능 테스트."""
    from synapstock.infrastructure.adapters.local.statistics_repo import LocalStatisticsRepository
    from synapstock.application.services.statistics_service import StatisticsService, RankingItem, DailyMarketRanking
    
    repo_dir = tmp_path / "stats"
    repo = LocalStatisticsRepository(data_root=str(repo_dir))
    service = StatisticsService(repository=repo)
    
    ranking = DailyMarketRanking(
        date="2026-04-08",
        market=MarketType.KOSPI,
        subject=SupplySubject.FOREIGN,
        items=[RankingItem(rank=1, name="테스트종목", amount=1234)]
    )
    
    # 저장
    service.save_rankings([ranking])
    
    # 불러오기 (캐시 확인)
    loaded = service.get_daily_ranking("2026-04-08", MarketType.KOSPI, SupplySubject.FOREIGN)
    
    assert loaded is not None
    assert loaded.items[0].name == "테스트종목"
    assert (repo_dir / "2026-04-08_KOSPI_FOREIGN.json").exists()
