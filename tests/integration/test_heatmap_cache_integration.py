from datetime import datetime, timedelta
from unittest.mock import MagicMock
import pytest
import pandas as pd
from synapstock.application.services.heatmap.heatmap_service import HeatmapService
from synapstock.domain.heatmap.models import Heatmap, Theme

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
