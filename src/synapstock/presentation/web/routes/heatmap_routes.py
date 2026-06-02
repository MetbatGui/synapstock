from fastapi import APIRouter, HTTPException, Query
from synapstock.application.services.heatmap.heatmap_service import HeatmapService
from synapstock.application.services.heatmap.view_model_builder import HeatmapViewModelBuilder

router = APIRouter(prefix="/api/heatmap", tags=["heatmap"])

@router.get("/data")
async def get_heatmap_plotly_data(
    show_categories: bool = Query(True, description="하위 카테고리(섹터) 표시 여부"),
    show_stocks: bool = Query(True, description="개별 종목(주식) 상세 표시 여부"),
    force_refresh: bool = Query(False, description="캐시 강제 초기화 여부")
):
    """
    KRX 실시간 시세와 로컬 테마 분류 데이터를 결합하여
    Plotly.js Treemap 시각화에 최적화된 Flat JSON Array 구조를 반환합니다.
    """
    try:
        # 1. 서비스 로드
        service = HeatmapService()
        themes = service.get_themes(force_refresh=force_refresh)
        
        if not themes:
            raise HTTPException(status_code=503, detail="테마 데이터를 수집하거나 빌드하는 데 실패했습니다. 잠시 후 다시 시도하십시오.")
            
        group_stats = service.get_group_stats_models(themes)
        
        # 2. ViewModel 변환기 호출 (서비스 활용)
        view_model = HeatmapViewModelBuilder.build(
            themes=themes,
            group_stats=group_stats,
            show_categories=show_categories,
            show_stocks=show_stocks
        )
        
        # 3. Plotly.js 최적화 DTO 형식 응답
        return {
            "ids": view_model.get_ids(),
            "labels": view_model.get_labels(),
            "parents": view_model.get_parents(),
            "values": view_model.get_values(),
            "colors": view_model.get_colors(),
            "customdata": view_model.get_colors(),  # 툴팁이나 호버용으로 등락률을 customdata에 직접 연동
            "tickers": view_model.get_tickers(),
            "title": view_model.title,
            "expired_at": HeatmapService.get_expired_at().isoformat() if HeatmapService.get_expired_at() else None
        }
        
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Failed to serve heatmap API data")
        raise HTTPException(status_code=500, detail=f"히트맵 데이터를 제공하는 중 에러가 발생했습니다: {str(e)}")
