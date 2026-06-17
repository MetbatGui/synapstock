"""리포트 인덱스 동기화 및 파일 서빙 API 라우터.

로컬 인덱스(``list.json``, ``reports.json``) 조회, Google Drive 강제 동기화,
PDF 파일 온디맨드 다운로드 및 서빙 엔드포인트를 제공합니다.
"""

import logging

logger = logging.getLogger(__name__)

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from evenezer.presentation.web.core.dependencies import report_service

router = APIRouter()


@router.get("/api/reports/local", response_model=None)
async def get_local_reports(name: str):
    """지정된 종목명이 매칭되는 리포트 목록을 반환합니다.

    Args:
        name: 조회할 종목명.

    Returns:
        종목에 매칭되는 리포트 목록 리스트. 에러 시 500 JSONResponse.
    """
    try:
        if not report_service:
            return []

        reports = await report_service.get_reports_by_stock(name)
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
    """전체 종목별 리포트 수량을 집계하여 반환합니다.

    Returns:
        종목명을 키로 하고 리포트 개수를 값으로 하는 딕셔너리. 에러 시 500 JSONResponse.
    """
    try:
        if not report_service:
            return {}
        return await report_service.get_report_counts()
    except Exception as e:
        logger.error(f"Error in get_report_counts: {e}")
        return JSONResponse(status_code=500, content={"message": str(e)})


@router.post("/api/reports/sync", response_model=None)
async def sync_reports_index():
    """Google Drive에서 최신 인덱스 파일을 강제로 동기화합니다.

    Returns:
        동기화 성공 또는 실패 여부를 담은 메시지 딕셔너리.
    """
    if not report_service:
        return JSONResponse(status_code=400, content={"message": "Cloud sync not configured"})

    try:
        updated = await report_service.sync_index()
        if updated:
            return {"status": "success", "message": f"Updated from cloud: {', '.join(updated)}"}
        return {"status": "error", "message": "Index files not found in cloud"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})


@router.get("/report_files/{filename}", response_model=None)
async def serve_report_file(filename: str):
    """지정된 PDF 리포트 파일을 서빙합니다.

    로컬에 파일이 없을 경우 구글 드라이브로부터 실시간 다운로드를 시도하여 서빙합니다.

    Args:
        filename: 서빙할 리포트 파일명.

    Returns:
        FileResponse를 통한 PDF 파일 바이너리 스트림 또는 404/400 오류 메시지.
    """
    from fastapi.responses import FileResponse

    if not report_service:
        return JSONResponse(status_code=400, content={"message": "Cloud sync not configured"})

    local_path = await report_service.get_file_content_path(filename)
    if local_path:
        return FileResponse(local_path)

    return JSONResponse(status_code=404, content={"message": "File not found locally or in cloud"})
