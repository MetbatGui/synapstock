"""리포트 인덱스 동기화 및 파일 서빙 API 라우터.

로컬 인덱스(``list.json``, ``reports.json``) 조회, Google Drive 강제 동기화,
PDF 파일 온디맨드 다운로드 및 서빙 엔드포인트를 제공합니다.
"""

import logging

logger = logging.getLogger(__name__)

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from synapstock.presentation.web.core.dependencies import report_service

router = APIRouter()


@router.get("/api/reports/local", response_model=None)
async def get_local_reports(name: str):
    """지정된 종목명이 포함된 리포트 목록을 반환합니다."""
    try:
        if not report_service:
            return []

        reports = report_service.get_reports_by_stock(name)
        return [
            {
                "filename": r.filename,
                "url": r.url,
                "date": r.date,
                "provider": r.provider,
                "title": r.title,
            }
            for r in reports
        ]
    except Exception as e:
        logger.error(f"Error in get_local_reports: {e}")
        return JSONResponse(status_code=500, content={"message": str(e)})


@router.get("/api/reports/counts", response_model=None)
async def get_report_counts():
    """전체 종목별 리포트 수량을 집계하여 반환합니다."""
    try:
        if not report_service:
            return {}
        return report_service.get_report_counts()
    except Exception as e:
        logger.error(f"Error in get_report_counts: {e}")
        return JSONResponse(status_code=500, content={"message": str(e)})


@router.post("/api/reports/sync", response_model=None)
async def sync_reports_index():
    """Google Drive에서 최신 인덱스 파일을 강제로 동기화합니다."""
    if not report_service:
        return JSONResponse(status_code=400, content={"message": "Cloud sync not configured"})

    try:
        updated = report_service.sync_index()
        if updated:
            return {"status": "success", "message": f"Updated from cloud: {', '.join(updated)}"}
        return {"status": "error", "message": "Index files not found in cloud"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})


@router.get("/report_files/{filename}", response_model=None)
async def serve_report_file(filename: str):
    """PDF 리포트 파일을 서빙합니다 (로컬 없으면 클라우드 자동 다운로드)."""
    from fastapi.responses import FileResponse

    if not report_service:
        return JSONResponse(status_code=400, content={"message": "Cloud sync not configured"})

    local_path = report_service.get_file_content_path(filename)
    if local_path:
        return FileResponse(local_path)

    return JSONResponse(status_code=404, content={"message": "File not found locally or in cloud"})
