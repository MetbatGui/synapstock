"""수급 통계(Statistics) API 라우터.

일별 수급 순위 분석 데이터 및 분석 가능한 날짜 목록을 제공합니다.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from synapstock.domain.statistics.models import MarketType, SupplySubject
from synapstock.presentation.web.core.dependencies import statistics_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/statistics", tags=["statistics"])


@router.get("/daily-ranking", response_model=None)
async def get_daily_ranking(
    date: str = Query(..., description="조회 날짜 (YYYY-MM-DD)"),
    market: MarketType = Query(MarketType.KOSPI, description="시장 구분 (KOSPI/KOSDAQ)"),
    subject: SupplySubject = Query(SupplySubject.FOREIGN, description="수급 주체 (FOREIGN/INSTITUTION)"),
):
    """특정일의 분석된 수급 순위를 가져옵니다."""
    try:
        if not statistics_service:
            raise HTTPException(status_code=500, detail="Statistics service not available")

        result = await statistics_service.get_analyzed_ranking(date, market, subject)
        if not result:
            # 데이터가 없는 경우 404가 아닌 빈 결과 또는 메시지 반환 (UI 처리를 위해)
            return {
                "date": date,
                "market": market,
                "subject": subject,
                "items": [],
                "message": "No data available for this date",
            }

        return result
    except Exception as e:
        logger.error(f"Error in get_daily_ranking: {e}")
        return JSONResponse(status_code=500, content={"message": str(e)})


@router.get("/daily-summary", response_model=None)
async def get_daily_summary(date: str = Query(..., description="조회 날짜 (YYYY-MM-DD)")):
    """지정된 날짜의 코스피/코스닥 × 외국인/기관 4가지 조합 수급 순위를 모두 가져옵니다."""
    try:
        if not statistics_service:
            raise HTTPException(status_code=500, detail="Statistics service not available")

        return await statistics_service.get_daily_summary(date)
    except Exception as e:
        logger.error(f"Error in get_daily_summary: {e}")
        return JSONResponse(status_code=500, content={"message": str(e)})


@router.get("/monthly-summary", response_model=None)
async def get_monthly_summary(month: str = Query(..., description="조회 월 (YYYY-MM)")):
    """지정된 월의 코스피/코스닥 × 외국인/기관 4가지 조합 월간 누적 수급 순위를 가져옵니다."""
    try:
        if not statistics_service:
            raise HTTPException(status_code=500, detail="Statistics service not available")

        return {
            "month": month,
            "KOSPI": {
                "FOREIGN": await statistics_service.get_monthly_ranking(month, MarketType.KOSPI, SupplySubject.FOREIGN),
                "INSTITUTION": await statistics_service.get_monthly_ranking(
                    month, MarketType.KOSPI, SupplySubject.INSTITUTION
                ),
            },
            "KOSDAQ": {
                "FOREIGN": await statistics_service.get_monthly_ranking(month, MarketType.KOSDAQ, SupplySubject.FOREIGN),
                "INSTITUTION": await statistics_service.get_monthly_ranking(
                    month, MarketType.KOSDAQ, SupplySubject.INSTITUTION
                ),
            },
        }
    except Exception as e:
        logger.error(f"Error in get_monthly_summary: {e}")
        return JSONResponse(status_code=500, content={"message": str(e)})


@router.get("/available-dates", response_model=None)
async def get_available_dates(
    market: MarketType = Query(MarketType.KOSPI), subject: SupplySubject = Query(SupplySubject.FOREIGN)
):
    """통계 데이터가 존재하는 날짜 목록을 반환합니다."""
    try:
        if not statistics_service:
            return []

        if hasattr(statistics_service, "list_available_dates"):
            return statistics_service.list_available_dates(market, subject)
        return []
    except Exception as e:
        logger.error(f"Error in get_available_dates: {e}")
        return []


@router.post("/sync", response_model=None)
async def sync_statistics():
    """구글 드라이브로부터 최신 수급 통계 데이터를 동기화합니다."""
    try:
        if not statistics_service:
            raise HTTPException(status_code=500, detail="Statistics service not available")

        count = await statistics_service.sync_recent_data(limit=5)
        return {"status": "success", "message": f"{count}일치 데이터가 동기화되었습니다.", "synced_count": count}
    except Exception as e:
        logger.error(f"Error in sync_statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ceiling-report", response_model=None)
async def get_ceiling_report(
    date: str = Query(..., description="조회 날짜 (YYYY-MM-DD)"),
    force_sync: bool = Query(False, description="강제 동기화 여부"),
):
    """특정 날짜의 상한가 분석 리포트를 가져옵니다."""
    try:
        if not statistics_service:
            raise HTTPException(status_code=500, detail="Statistics service not available")

        result = await statistics_service.get_ceiling_analysis(date, force_sync=force_sync)
        if not result:
            return {"date": date, "items": [], "message": "No ceiling data available for this date"}

        return result
    except Exception as e:
        logger.error(f"Error in get_ceiling_report: {e}")
        return JSONResponse(status_code=500, content={"message": str(e)})


@router.get("/ceiling-years", response_model=None)
async def get_ceiling_years():
    """상한가 분석이 가능한 연도 목록을 반환합니다."""
    try:
        if not statistics_service:
            return [datetime.now().strftime("%Y")]

        return await statistics_service.list_available_ceiling_years()
    except Exception as e:
        logger.error(f"Error in get_ceiling_years: {e}")
        return [datetime.now().strftime("%Y")]


@router.get("/ceiling-dates", response_model=None)
async def get_ceiling_dates(year: str | None = Query(None, description="조회할 연도 (YYYY)")):
    """특정 연도의 상한가 분석 데이터가 존재하는 날짜 목록을 반환합니다."""
    try:
        if not statistics_service:
            return []

        return await statistics_service.list_available_ceiling_dates(year=year)
    except Exception as e:
        logger.error(f"Error in get_ceiling_dates: {e}")
        return []


@router.get("/capital-increase", response_model=None)
async def get_capital_increase(force_sync: bool = Query(False, description="강제 동기화 여부")):
    """유상증자 공시 분석 데이터를 가져옵니다."""
    try:
        if not statistics_service:
            raise HTTPException(status_code=500, detail="Statistics service not available")

        items = await statistics_service.get_capital_increase_data(force_sync=force_sync)
        return {"count": len(items), "items": items}
    except Exception as e:
        logger.error(f"Error in get_capital_increase: {e}")
        return JSONResponse(status_code=500, content={"message": str(e)})


@router.get("/bonus-issue", response_model=None)
async def get_bonus_issue(force_sync: bool = Query(False, description="강제 동기화 여부")):
    """무상증자 공시 분석 데이터를 가져옵니다."""
    try:
        if not statistics_service:
            raise HTTPException(status_code=500, detail="Statistics service not available")

        items = await statistics_service.get_bonus_issue_data(force_sync=force_sync)
        return {"count": len(items), "items": items}
    except Exception as e:
        logger.error(f"Error in get_bonus_issue: {e}")
        return JSONResponse(status_code=500, content={"message": str(e)})


@router.get("/convertible-bond", response_model=None)
async def get_convertible_bond(force_sync: bool = Query(False, description="강제 동기화 여부")):
    """전환사채(CB) 발행 결정 공시 분석 데이터를 가져옵니다."""
    try:
        if not statistics_service:
            raise HTTPException(status_code=500, detail="Statistics service not available")

        items = await statistics_service.get_convertible_bond_data(force_sync=force_sync)
        return {"count": len(items), "items": items}
    except Exception as e:
        logger.error(f"Error in get_convertible_bond: {e}")
        return JSONResponse(status_code=500, content={"message": str(e)})


@router.post("/convertible-bond/sync", response_model=None)
async def sync_convertible_bond():
    """전환사채(CB) 데이터를 구글 드라이브와 동기화합니다."""
    try:
        if not statistics_service:
            raise HTTPException(status_code=500, detail="Statistics service not available")
        return await statistics_service.sync_convertible_bond_data()
    except Exception as e:
        logger.error(f"Error in sync_convertible_bond: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bond-with-warrants", response_model=None)
async def get_bond_with_warrants(force_sync: bool = Query(False, description="강제 동기화 여부")):
    """신주인수권부사채(BW) 발행 결정 공시 분석 데이터를 가져옵니다."""
    try:
        if not statistics_service:
            raise HTTPException(status_code=500, detail="Statistics service not available")

        items = await statistics_service.get_bw_data(force_sync=force_sync)
        return {"count": len(items), "items": items}
    except Exception as e:
        logger.error(f"Error in get_bond_with_warrants: {e}")
        return JSONResponse(status_code=500, content={"message": str(e)})


@router.post("/bond-with-warrants/sync", response_model=None)
async def sync_bond_with_warrants():
    """신주인수권부사채(BW) 데이터를 구글 드라이브와 동기화합니다."""
    try:
        if not statistics_service:
            raise HTTPException(status_code=500, detail="Statistics service not available")
        return await statistics_service.sync_bw_data()
    except Exception as e:
        logger.error(f"Error in sync_bond_with_warrants: {e}")
        raise HTTPException(status_code=500, detail=str(e))
@router.get("/new-listing", response_model=None)
async def get_new_listing(force_sync: bool = Query(False, description="강제 동기화 여부")):
    """신규상장주(IPO) 분석 데이터를 가져옵니다."""
    try:
        if not statistics_service:
            raise HTTPException(status_code=500, detail="Statistics service not available")

        items = await statistics_service.get_new_listing_data(force_sync=force_sync)
        return {"count": len(items), "items": items}
    except Exception as e:
        logger.error(f"Error in get_new_listing: {e}")
        return JSONResponse(status_code=500, content={"message": str(e)})
