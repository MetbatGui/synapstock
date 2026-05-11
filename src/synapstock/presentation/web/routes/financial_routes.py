from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from typing import List

from synapstock.domain.financials.models import FinancialMetric
from synapstock.presentation.web.core.dependencies import financial_service

router = APIRouter(prefix="/api/financials", tags=["financials"])

@router.get("/top-growers")
async def get_top_growers(
    metric: FinancialMetric = Query(..., description="분석할 재무 지표 (REVENUE, OPERATING_PROFIT, NET_INCOME)"),
    quarter: str | None = Query(None, description="기준 분기 (미입력 시 최신 분기 자동 선택)"),
    top_n: int = Query(500, description="추출할 상위 종목 수")
):
    """전년 동기 대비 실적이 크게 개선된 상위 종목 리스트를 반환합니다."""
    try:
        results = financial_service.get_top_growers(
            metric=metric,
            target_quarter=quarter,
            top_n=top_n
        )
        
        # 결과를 JSON 직렬화 가능한 형태로 변환
        return [
            {
                "stock_name": item.stock_name,
                "current_value": item.current_value,
                "prev_value": item.prev_value,
                "change_rate": item.change_rate
            }
            for item in results
        ]
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error in get_top_growers: {e}")
        return JSONResponse(status_code=500, content={"message": str(e)})
