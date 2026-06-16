import pytest
from evenezer.application.services.heatmap.heatmap_service import HeatmapService
from evenezer.application.services.heatmap.view_model_builder import HeatmapViewModelBuilder

def test_heatmap_service_initialization():
    """HeatmapService의 성공적인 인스턴스화 여부 검증"""
    service = HeatmapService()
    assert service is not None

def test_heatmap_data_pipeline_flow():
    """테마 로드, 실시간 KRX 가격 결합, 그룹 가중치 통계 및 DTO 변환 전체 흐름 검증"""
    service = HeatmapService()
    themes = service.get_themes()
    
    # 테마 목록 수집 확인
    assert themes is not None
    
    if themes:
        # 그룹 통계 정보 계산 검증
        group_stats = service.get_group_stats_models(themes)
        assert group_stats is not None
        
        # Plotly.js 최적화 DTO Flat JSON 변환 검증
        view_model = HeatmapViewModelBuilder.build(
            themes=themes,
            group_stats=group_stats,
            show_categories=True,
            show_stocks=True
        )
        assert view_model is not None
        
        # DTO 노드 리스트 구성 및 크기 일치성 검증
        ids = view_model.get_ids()
        labels = view_model.get_labels()
        colors = view_model.get_colors()
        parents = view_model.get_parents()
        
        assert len(ids) > 0
        assert len(labels) == len(ids)
        assert len(colors) == len(ids)
        assert len(parents) == len(ids)
        
        # 반올림 수치 커팅 검증 (소수점 둘째 자리)
        # float 형태의 colors가 round(val, 2) 와 완벽히 일치하는지 비교
        for val in colors:
            if val is not None:
                assert val == round(val, 2)
