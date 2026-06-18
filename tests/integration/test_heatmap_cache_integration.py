from datetime import datetime, timedelta
from unittest.mock import MagicMock
import pytest
import pandas as pd
from evenezer.application.services.heatmap.heatmap_service import HeatmapService
from evenezer.domain.heatmap.models import Heatmap, Theme

def test_heatmap_cache_hit_and_expiry_refresh():
    """통합 테스트: 캐시 힛 검증 및 만료 시 갱신(Refresh) 라이프사이클 검증"""
    
    # 0. 초기화: 이전 잔존 캐시 클리어
    HeatmapService._cache_data = None
    HeatmapService._expired_at = None
    
    # 1. 의존성 Mocking 세팅 (호출 횟수를 추적하기 위함)
    mock_file_repo = MagicMock()
    mock_krx_repo = MagicMock()
    
    # 기본 반환 모형 데이터 설정 (데이터 파이프라인 무난히 통과 유도)
    mock_heatmap = Heatmap()
    mock_heatmap.add_theme(Theme(name="2차전지"))
    mock_file_repo.load_heatmap.return_value = mock_heatmap
    
    mock_krx_repo.fetch_listing.return_value = pd.DataFrame([
        {"Name": "LG에너지솔루션", "Code": "373220", "Marcap": 100000000000000.0, "ChagesRatio": 1.5, "테마": "2차전지"}
    ])
    
    service = HeatmapService(loader=mock_file_repo, krx_repo=mock_krx_repo)
    
    # 2. 첫 번째 호출 (Cache Miss)
    themes_first = service.get_themes()
    
    assert len(themes_first) > 0
    assert mock_file_repo.load_heatmap.call_count == 1
    assert mock_krx_repo.fetch_listing.call_count == 1
    assert HeatmapService._cache_data is not None
    assert HeatmapService._expired_at is not None
    
    # 만료 시각이 대략 10분 후로 지정되었는지 확인 (9분 ~ 11분 바운더리 체크)
    expected_expiry_min = datetime.now() + timedelta(minutes=9)
    expected_expiry_max = datetime.now() + timedelta(minutes=11)
    assert expected_expiry_min < HeatmapService._expired_at < expected_expiry_max
    
    # 3. 두 번째 호출 (Cache Hit 검증)
    # 새로운 인스턴스를 만들더라도 클래스 레벨 캐시이므로 캐시 힛이 발생해야 함
    service_another = HeatmapService(loader=mock_file_repo, krx_repo=mock_krx_repo)
    themes_second = service_another.get_themes()
    
    # 동일한 캐시 객체를 즉시 반환했는지 검사
    assert themes_second is themes_first
    # DB/어댑터 호출 횟수가 최초 1회 이후로 더 늘어나지 않았음을 검증 (캐시 힛 확인!)
    assert mock_file_repo.load_heatmap.call_count == 1
    assert mock_krx_repo.fetch_listing.call_count == 1
    
    # 4. 강제 만료 유도 (Expiry)
    # _expired_at 시각을 과거 1초 전으로 인위적 조작
    HeatmapService._expired_at = datetime.now() - timedelta(seconds=1)
    
    # 5. 세 번째 호출 (Cache Expiry & Refresh 검증)
    themes_third = service_another.get_themes()
    
    # 캐시가 만료되어 새로 불러왔으므로 첫 번째와 다른 인스턴스가 됨
    assert themes_third is not themes_first
    # 어댑터 호출 횟수가 다시 +1 증가하여 신규 수집(Enrichment)이 실행되었음을 검증
    assert mock_file_repo.load_heatmap.call_count == 2
    assert mock_krx_repo.fetch_listing.call_count == 2
    
    # 만료 시간도 다시 현재 기준 10분 후로 갱신되었음을 검증
    assert expected_expiry_min < HeatmapService._expired_at < (datetime.now() + timedelta(minutes=11))

    # 6. 네 번째 호출 (force_refresh = True 검증)
    # 현재 캐시가 안전하게 살아있는 상황에서 force_refresh=True를 전달해 강제 갱신 작동 검증
    themes_fourth = service_another.get_themes(force_refresh=True)
    
    # 캐시가 강제 무효화 및 재생성되었으므로 세 번째 호출 결과와 다른 인스턴스여야 함
    assert themes_fourth is not themes_third
    # 호출 횟수가 3회로 증가했음을 검증 (캐시 우회 작동 확인)
    assert mock_file_repo.load_heatmap.call_count == 3
    assert mock_krx_repo.fetch_listing.call_count == 3


def test_heatmap_cache_with_list_of_dict():
    """통합 테스트: krx_repo가 list[dict] 표준 형식을 반환할 때의 캐싱 및 데이터 enrichment 검증"""
    from evenezer.domain.heatmap.models import Category, Stock
    from evenezer.domain.heatmap.value_objects import MarketCap, ChangeRatio

    # 0. 초기화: 이전 잔존 캐시 클리어
    HeatmapService._cache_data = None
    HeatmapService._expired_at = None
    
    # 1. 의존성 Mocking 세팅
    mock_file_repo = MagicMock()
    mock_krx_repo = MagicMock()
    
    mock_heatmap = Heatmap()
    theme = Theme(name="반도체")
    category = Category(name="기본")
    stock = Stock(name="삼성전자", code="005930", market_cap=MarketCap.zero(), change_ratio=ChangeRatio.zero())
    category.add_stock(stock)
    theme.add_category(category)
    mock_heatmap.add_theme(theme)
    
    mock_file_repo.load_heatmap.return_value = mock_heatmap
    
    # 표준 list[dict] 형태 반환
    mock_krx_repo.fetch_listing.return_value = [
        {"Name": "삼성전자", "Code": "005930", "Marcap": 400000000000000.0, "ChagesRatio": 1.5, "테마": "반도체"}
    ]
    
    service = HeatmapService(loader=mock_file_repo, krx_repo=mock_krx_repo)
    
    # 2. 첫 번째 호출 (Cache Miss) 및 데이터 결합 확인
    themes = service.get_themes()
    assert len(themes) > 0
    assert themes[0].name == "반도체"
    assert len(themes[0].stocks) == 1
    assert themes[0].stocks[0].name == "삼성전자"
    assert themes[0].stocks[0].code == "005930"
    assert themes[0].stocks[0].market_cap.value_in_won == 400000000000000.0
    assert themes[0].stocks[0].change_ratio.value == 1.5
    
    # 3. 캐시가 채워졌는지 확인
    assert HeatmapService._cache_data is not None



