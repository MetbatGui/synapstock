from fastapi import APIRouter, Query

from evenezer.domain.financials.models import FinancialMetric
from evenezer.presentation.web.core.dependencies import financial_service

router = APIRouter(prefix="/api/financials", tags=["financials"])


@router.get("/quarters")
async def get_quarters(metric: FinancialMetric = Query(FinancialMetric.OPERATING_PROFIT)):
    """지정된 재무 지표에 대해 데이터가 존재하는 모든 분기 목록을 조회합니다.

    Args:
        metric: 조회할 재무 지표 구분.

    Returns:
        선택 가능한 분기 식별자 리스트.
    """
    return financial_service.get_available_quarters(metric)


@router.get("/top-growers")
async def get_top_growers(
    metric: FinancialMetric = Query(..., description="분석할 재무 지표 (REVENUE, OPERATING_PROFIT, NET_INCOME)"),
    target_quarter: str | None = Query(None, description="기준 분기 (미입력 시 최신 분기 자동 선택)"),
    top_n: int = Query(500, description="추출할 상위 종목 수"),
):
    """직전 대비 실적 성장률이 우수한 상위 종목 목록을 조회합니다.

    일반 성장 종목군(normal)과 흑자전환 종목군(turnaround)으로 분류하여 반환합니다.

    Args:
        metric: 분석 대상 재무 지표.
        target_quarter: 기준 분기 식별자. None일 경우 최신 분기를 자동 탐색하여 적용합니다.
        top_n: 조회할 상위 종목 개수 한도.

    Returns:
        일반 성장 종목 및 흑자전환 종목 정보 딕셔너리.

    Raises:
        HTTPException: 데이터 조회 에러 발생 시 500 응답 코드를 반환합니다.
    """
    try:
        result_dict = financial_service.get_top_growers(metric, target_quarter, top_n)

        # 결과를 JSON 직렬화 가능한 형태로 변환
        def map_item(item):
            return {
                "stock_name": item.stock_name,
                "current_value": item.current_value,
                "prev_value": item.prev_value,
                "pre_prev_value": item.pre_prev_value,
                "change_rate": item.change_rate,
                "history": item.history,
            }

        return {
            "normal": [map_item(i) for i in result_dict["normal"]],
            "turnaround": [map_item(i) for i in result_dict["turnaround"]],
        }
    except Exception as e:
        import logging

        logging.getLogger(__name__).error(f"Error in get_top_growers: {e}")
        from fastapi import HTTPException

        raise HTTPException(status_code=500, detail=str(e))


@router.get("/consecutive-growers")
async def get_consecutive_growers(
    metric: FinancialMetric = Query(..., description="분산할 재무 지표"),
    target_quarter: str | None = Query(None, description="기준 분기"),
    count: int = Query(3, description="연속 성장 분기 수 (2, 3, 4)"),
):
    """지정된 분기를 포함해 여러 분기 연속으로 실적이 전 분기 대비 상승한 종목 목록을 조회합니다.

    Args:
        metric: 분석 대상 재무 지표.
        target_quarter: 기준 분기 식별자. None일 경우 최신 분기를 자동 적용합니다.
        count: 연속 성장 판별을 수행할 분기 수.

    Returns:
        연속 성장 조건에 부합하는 일반 성장 및 흑자전환 종목 정보 딕셔너리.

    Raises:
        HTTPException: 데이터 조회 에러 발생 시 500 응답 코드를 반환합니다.
    """
    try:
        result_dict = financial_service.get_consecutive_growers(metric, target_quarter, count)

        def map_item(item):
            return {
                "stock_name": item.stock_name,
                "current_value": item.current_value,
                "prev_value": item.prev_value,
                "pre_prev_value": item.pre_prev_value,
                "change_rate": item.change_rate,
                "history": item.history,
            }

        return {
            "normal": [map_item(i) for i in result_dict["normal"]],
            "turnaround": [map_item(i) for i in result_dict["turnaround"]],
        }
    except Exception as e:
        import logging

        logging.getLogger(__name__).error(f"Error in get_consecutive_growers: {e}")
        from fastapi import HTTPException

        raise HTTPException(status_code=500, detail=str(e))
