"""Miro 보드 관련 API 라우터.

보드 목록 조회, 계층형 데이터 로드, Miro 동기화, 노드/종목/리포트 CRUD 엔드포인트를 제공합니다.
"""
import asyncio
import json
import threading
from typing import cast

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse

from synapstock.presentation.web.core.dependencies import (
    command_service,
    media_service,
    query_service,
    sync_service,
)
from synapstock.presentation.web.core.websocket_manager import manager

router = APIRouter()


@router.get("/api/boards", response_model=None)
async def get_boards() -> list[dict] | JSONResponse:
    """사용 가능한 마인드맵 보드 메타 정보 목록을 반환합니다.

    Returns:
        list[dict]: 보드 id와 name을 포함하는 리스트.
    """
    return cast(list[dict], query_service.get_boards_info())


@router.get("/api/board", response_model=None)
async def get_board_data(name: str) -> dict | JSONResponse:
    """특정 보드의 계층형 트리 데이터를 반환합니다.

    Args:
        name (str): 조회할 보드 파일명.

    Returns:
        dict: 루트 노드를 포함한 계층형 트리 구조. 키: ``name``, ``nodes``, ``stocks``.

    Raises:
        JSONResponse (404): 보드를 찾을 수 없는 경우.
    """
    try:
        board = query_service.load_board(name)

        def to_dict(node):
            return {
                "name": node.name,
                "nodes": [to_dict(n) for n in node.nodes],
                "stocks": [
                    {"name": s.name, "ticker": s.ticker, "reports": s.reports, "news": s.news}
                    for s in node.stocks
                ],
            }

        return cast(dict, to_dict(board.root))
    except Exception as e:
        return JSONResponse(status_code=404, content={"message": str(e)})


@router.post("/api/sync", response_model=None)
async def trigger_sync(name: str) -> dict | JSONResponse:
    """백그라운드 스레드에서 Miro 동기화를 시작합니다.

    동기화 진행 상황은 활성 WebSocket 연결을 통해 실시간으로 브로드캐스트됩니다.
    요청은 즉시 ``{"status": "started"}`` 를 반환하며, 동기화는 비동기로 처리됩니다.

    Args:
        name (str): 동기화할 보드 파일명.

    Returns:
        dict: ``{"status": "started"}`` 형태의 응답.
    """
    def do_sync():
        async def log_callback(msg, val):
            await manager.broadcast(json.dumps({"type": "log", "message": msg, "progress": val}))

        try:
            board = query_service.load_board(name)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            def sync_progress(m, v):
                loop.run_until_complete(log_callback(m, v))

            sync_service.sync_with_miro(board, progress_callback=sync_progress)
        except Exception as e:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(log_callback(f"Error: {str(e)}", 0))

    thread = threading.Thread(target=do_sync, daemon=True)
    thread.start()
    return {"status": "started"}


@router.post("/api/node/add", response_model=None)
async def add_node(board: str, parent: str, name: str) -> dict | JSONResponse:
    """지정된 부모 노드 아래에 새 폴더 노드를 추가합니다.

    Args:
        board (str): 대상 보드 파일명.
        parent (str): 새 노드를 추가할 부모 노드 이름.
        name (str): 생성할 새 노드의 이름.

    Returns:
        dict: ``{"status": "success"}`` 또는 404 오류 응답.
    """
    success = command_service.add_node(board, parent, name)
    if success:
        return {"status": "success"}
    return JSONResponse(status_code=404, content={"message": "Parent node not found"})


@router.post("/api/node/delete", response_model=None)
async def delete_node(board: str, name: str) -> dict | JSONResponse:
    """노드를 삭제하고 하위 항목을 부모 노드로 흡수합니다.

    루트 노드는 삭제할 수 없습니다.

    Args:
        board (str): 대상 보드 파일명.
        name (str): 삭제할 노드 이름.

    Returns:
        dict: ``{"status": "success"}`` 또는 400 오류 응답.
    """
    success = command_service.delete_node(board, name)
    if success:
        return {"status": "success"}
    return JSONResponse(
        status_code=400,
        content={"message": "Delete failed (Root cannot be deleted or node not found)"},
    )


@router.post("/api/stock/add", response_model=None)
async def add_stock(board: str, parent: str, name: str, ticker: str) -> dict | JSONResponse:
    """지정된 부모 노드 아래에 새 종목을 추가합니다.

    Args:
        board (str): 대상 보드 파일명.
        parent (str): 종목을 추가할 부모 노드 이름.
        name (str): 종목명.
        ticker (str): 종목 티커 심볼.

    Returns:
        dict: ``{"status": "success"}`` 또는 404 오류 응답.
    """
    success = command_service.add_stock(board, parent, name, ticker)
    if success:
        return {"status": "success"}
    return JSONResponse(status_code=404, content={"message": "Parent node not found"})


@router.delete("/api/stock/delete", response_model=None)
async def delete_stock(board: str, ticker: str) -> dict | JSONResponse:
    """보드에서 특정 종목을 삭제합니다.

    Args:
        board (str): 대상 보드 파일명.
        ticker (str): 삭제할 종목의 티커 심볼.

    Returns:
        dict: ``{"status": "success"}`` 또는 404 오류 응답.
    """
    success = command_service.delete_stock(board, ticker)
    if success:
        return {"status": "success"}
    return JSONResponse(status_code=404, content={"message": "Stock not found in board"})


@router.post("/api/stock/news/add", response_model=None)
async def add_stock_news(board: str, ticker: str, title: str, date: str, url: str) -> dict | JSONResponse:
    """지정된 종목에 새 뉴스를 추가합니다."""
    success = command_service.add_stock_news(board, ticker, title, date, url)
    if success:
        return {"status": "success"}
    return JSONResponse(status_code=404, content={"message": "Stock not found"})


@router.delete("/api/stock/news/delete", response_model=None)
async def delete_stock_news(board: str, ticker: str, url: str) -> dict | JSONResponse:
    """보드에서 특정 뉴스를 삭제합니다."""
    success = command_service.delete_stock_news(board, ticker, url)
    if success:
        return {"status": "success"}
    return JSONResponse(status_code=404, content={"message": "Stock or news not found"})


@router.post("/api/stock/report/upload", response_model=None)
async def upload_stock_report(board: str, ticker: str, file: UploadFile = File(...)) -> dict | JSONResponse:
    """종목에 PDF 리포트 파일을 업로드합니다.

    Args:
        board (str): 대상 보드 파일명.
        ticker (str): 리포트를 업로드할 종목 티커.
        file (UploadFile): 업로드할 PDF 파일. ``.pdf`` 확장자만 허용합니다.

    Returns:
        dict: ``{"status": "success", "filename": str}`` 또는 오류 응답.

    Raises:
        JSONResponse (400): PDF 파일이 아닌 경우.
        JSONResponse (404): 해당 종목을 찾을 수 없는 경우.
        JSONResponse (500): 파일 처리 중 예외 발생 시.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return JSONResponse(status_code=400, content={"message": "PDF 파일만 업로드 가능합니다."})

    try:
        content = await file.read()
        success = media_service.add_stock_report(board, ticker, content, file.filename)
        if success:
            return {"status": "success", "filename": str(file.filename)}
        return JSONResponse(status_code=404, content={"message": "Stock not found"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})


@router.post("/api/stock/report/add_link", response_model=None)
async def add_stock_report_link(board: str, ticker: str, report_path: str) -> dict | JSONResponse:
    """종목에 리포트 링크를 추가합니다."""
    success = media_service.add_stock_report_link(board, ticker, report_path)
    if success:
        return {"status": "success"}
    return JSONResponse(status_code=404, content={"message": "Stock not found"})


@router.delete("/api/stock/report/delete", response_model=None)
async def delete_stock_report(board: str, ticker: str, report_path: str) -> dict | JSONResponse:
    """종목에서 리포트 링크를 제거합니다.

    Args:
        board (str): 대상 보드 파일명.
        ticker (str): 대상 종목 티커.
        report_path (str): 삭제할 리포트의 URL 경로.

    Returns:
        dict: ``{"status": "success"}`` 또는 오류 응답.

    Raises:
        JSONResponse (404): 종목 또는 리포트를 찾을 수 없는 경우.
        JSONResponse (500): 처리 중 예외 발생 시.
    """
    try:
        success = media_service.remove_stock_report(board, ticker, report_path)
        if success:
            return {"status": "success"}
        return JSONResponse(status_code=404, content={"message": "Stock or report not found"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})
