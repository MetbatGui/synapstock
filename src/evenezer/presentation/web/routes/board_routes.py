"""Miro 보드 관련 API 라우터.

보드 목록 조회, 계층형 데이터 로드, Miro 동기화, 노드/종목/리포트 CRUD 엔드포인트를 제공합니다.
"""

import asyncio
import json
import logging
import threading
from typing import cast

from fastapi import APIRouter, File, Response, UploadFile
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

from evenezer.presentation.web.core.dependencies import (
    board_file_sync_service,
    command_service,
    media_service,
    query_service,
    sync_service,
)
from evenezer.presentation.web.core.websocket_manager import manager

router = APIRouter()


@router.get("/api/boards", response_model=None)
async def get_boards() -> list[dict] | JSONResponse:
    """사용 가능한 마인드맵 보드 메타 정보 목록을 반환합니다.

    Returns:
        list[dict]: 보드 id와 name을 포함하는 리스트.
    """
    return cast(list[dict], query_service.get_boards_info())


@router.get("/api/board", response_model=None)
async def get_board_data(name: str, response: Response) -> dict | JSONResponse:
    """특정 보드의 계층형 트리 데이터를 반환합니다.

    Args:
        name (str): 조회할 보드 파일명.

    Returns:
        dict: 루트 노드를 포함한 계층형 트리 구조. 키: ``name``, ``nodes``, ``stocks``.

    Raises:
        JSONResponse (404): 보드를 찾을 수 없는 경우.
    """
    try:
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

        # 가상보드인 경우 매니페스트 로드하여 할당 메타데이터 확보 및 가상보드 파일 갱신 선수행
        manifest_meta = {}
        ticker_to_listing_date = {}

        if name == "virtual_신규상장주":
            # 1. 매니페스트에서 상장일 정보 로드 (listing_date 필드)
            try:
                from evenezer.presentation.web.core.dependencies import container
                manifest_path = container.config.board_dir / "board_sync_manifest.json"
                if manifest_path.exists():
                    raw = manifest_path.read_text(encoding="utf-8").strip()
                    if raw:
                        manifest_data = json.loads(raw)
                        manifest_meta = manifest_data.get("new_listings", {})
                        # 매니페스트의 listing_date로 연도 분류 맵 구성
                        for ticker, meta in manifest_meta.items():
                            l_date = meta.get("listing_date", "")
                            if l_date:
                                ticker_to_listing_date[ticker] = l_date
            except Exception as e:
                logger.error(f"Failed to load manifest for virtual board: {e}")

            # 2. 더미 테스트용 10개 종목 상장일 하드코딩 보정 (항상 적용)
            dummy_ipo_dates = {
                "990011": "2025-03-12",
                "990012": "2025-05-18",
                "990013": "2025-08-22",
                "990014": "2025-11-05",
                "990015": "2025-12-28",
                "990016": "2026-03-15",
                "990017": "2026-06-20",
                "990018": "2026-09-10",
                "990019": "2026-11-05",
                "990020": "2026-12-25",
            }
            for ticker, l_date in dummy_ipo_dates.items():
                ticker_to_listing_date[ticker] = l_date

        # 최신화된 보드 데이터를 디스크에서 로드
        board = query_service.load_board(name)

        # 루트 노드 경로 탐색
        root_path = next((p for p, n in board.nodes.items() if n.parent_path is None), name)

        def to_dict(path: str) -> dict:
            node = board.nodes.get(path)
            if not node:
                # 안전 장치
                return {"name": path.split("/")[-1], "nodes": [], "stocks": []}
                
            stocks_list = []
            for s in node.stocks:
                stock_dict = {"name": s.name, "ticker": s.ticker, "reports": s.reports, "news": s.news}
                if name == "virtual_신규상장주":
                    meta = manifest_meta.get(s.ticker, {})
                    stock_dict["status"] = meta.get("status", "PENDING")
                    stock_dict["current_board"] = meta.get("current_board", "virtual_신규상장주")
                    stock_dict["current_path"] = meta.get("current_path", [])
                stocks_list.append(stock_dict)

            # 직계 자식 노드 수집 및 정렬
            children = [p for p, n in board.nodes.items() if n.parent_path == path]
            children.sort()

            return {
                "name": node.name,
                "nodes": [to_dict(c) for c in children],
                "stocks": stocks_list,
            }

        # 신규상장주 보드인 경우 상장일 기반 가상 연도 계층 트리 노드로 동적 변환
        if name == "virtual_신규상장주":
            root_dict = to_dict(root_path)
            all_stocks = root_dict.get("stocks", [])

            # 상장일 기반 그룹화 (연도별)
            grouped = {}
            for s in all_stocks:
                l_date = ticker_to_listing_date.get(s["ticker"], "")
                year_str = "기타"

                # 점(.)을 대시(-)로 변환하여 유연하게 대처
                normalized_date = l_date.replace(".", "-") if l_date else ""
                if normalized_date and "-" in normalized_date:
                    parts = normalized_date.split("-")
                    if parts[0]:
                        year_str = parts[0] + "년"

                if year_str not in grouped:
                    grouped[year_str] = []
                grouped[year_str].append(s)

            # 계층형 노드로 변형
            nodes_list = []
            # 연도 내림차순 정렬
            for yr in sorted(grouped.keys(), reverse=True):
                nodes_list.append({
                    "name": yr,
                    "nodes": [],
                    "stocks": grouped[yr]
                })

            return {
                "name": board.root.name,
                "nodes": nodes_list,
                "stocks": []  # 루트 노드 바로 아래는 비워둠
            }

        return cast(dict, to_dict(root_path))
    except Exception as e:
        logger.error(f"Error loading board '{name}': {str(e)}")
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

    중복 등록 방지: 기등록된 테마 보드에 해당 종목이 존재할 경우 추가를 거부합니다.

    Args:
        board (str): 대상 보드 파일명.
        parent (str): 종목을 추가할 부모 노드 이름.
        name (str): 종목명.
        ticker (str): 종목 티커 심볼.

    Returns:
        dict: ``{"status": "success"}`` 또는 404/409 오류 응답.
    """
    # 중복 등록 여부 검증 (가상 보드 대기 종목은 검사에서 제외)
    existing_stock_info = query_service.get_stock_by_ticker(ticker)
    if existing_stock_info:
        _, existing_board, path = existing_stock_info
        if existing_board != "virtual_신규상장주" and board != "virtual_신규상장주":
            try:
                existing_board_obj = query_service.load_board(existing_board)
                board_display_name = existing_board_obj.name
            except Exception:
                board_display_name = existing_board.replace("theme_", "")
            
            path_str = " > ".join(path)
            return JSONResponse(
                status_code=409,
                content={
                    "status": "duplicate",
                    "message": f"이미 '{name}({ticker})' 종목이 [{board_display_name}] > {path_str} 에 존재하므로 추가할 수 없습니다."
                }
            )

    success = await command_service.add_stock(board, parent, name, ticker)
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
    success = await command_service.delete_stock(board, ticker)
    if success:
        return {"status": "success"}
    return JSONResponse(status_code=404, content={"message": "Stock not found in board"})





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
        success = await media_service.add_stock_report(board, ticker, content, file.filename)
        if success:
            return {"status": "success", "filename": str(file.filename)}
        return JSONResponse(status_code=404, content={"message": "Stock not found"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})


@router.post("/api/stock/report/add_link", response_model=None)
async def add_stock_report_link(board: str, ticker: str, report_path: str) -> dict | JSONResponse:
    """종목에 리포트 링크를 추가합니다.

    Args:
        board (str): 대상 보드 파일명.
        ticker (str): 대상 종목 티커.
        report_path (str): 추가할 리포트의 URL 또는 파일 경로.

    Returns:
        dict: ``{"status": "success"}`` 또는 404 오류 응답.
    """
    success = await media_service.add_stock_report_link(board, ticker, report_path)
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
        success = await media_service.remove_stock_report(board, ticker, report_path)
        if success:
            return {"status": "success"}
        return JSONResponse(status_code=404, content={"message": "Stock or report not found"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})


@router.post("/api/board/create", response_model=None)
async def create_board(name: str) -> dict | JSONResponse:
    """새로운 가상 보드를 생성합니다.

    Args:
        name (str): 생성할 가상 보드의 이름.

    Returns:
        dict: ``{"status": "success"}`` 또는 500 오류 응답.
    """
    success = command_service.create_board(name)
    if success:
        return {"status": "success"}
    return JSONResponse(status_code=500, content={"message": "Failed to create board"})


@router.post("/api/board/delete", response_model=None)
async def delete_board(name: str) -> dict | JSONResponse:
    """보드 전체를 삭제합니다.

    Args:
        name (str): 삭제할 보드 파일명.

    Returns:
        dict: ``{"status": "success"}`` 또는 404 오류 응답.
    """
    success = command_service.delete_board(name)
    if success:
        return {"status": "success"}
    return JSONResponse(status_code=404, content={"message": "Board not found or delete failed"})


@router.post("/api/board/virtual/sync", response_model=None)
async def sync_virtual_boards() -> dict | JSONResponse:
    """구글 드라이브 클라우드 저장소와 로컬 가상/테마 보드 파일들을 실시간으로 양방향 동기화합니다.

    Returns:
        dict: ``{"status": "success", "message": str}`` 또는 500 오류 응답.
    """
    try:
        success = await board_file_sync_service.sync_with_drive()
        if success:
            return {
                "status": "success",
                "message": "구글 드라이브 클라우드 저장소와 가상/테마 보드 양방향 동기화가 무사히 완료되었습니다."
            }
        return JSONResponse(
            status_code=500,
            content={"message": "구글 드라이브 파일 동기화 처리에 실패했습니다. 로그를 확인하세요."}
        )
    except Exception as e:
        logger.error(f"Error executing board drive sync: {str(e)}")
        return JSONResponse(status_code=500, content={"message": f"서버 동기화 오류: {str(e)}"})


from pydantic import BaseModel

class BatchIgnoreRequest(BaseModel):
    tickers: list[str]

@router.post("/api/board/virtual/batch-ignore", response_model=None)
async def batch_ignore_virtual_board_stocks(request: BatchIgnoreRequest) -> dict | JSONResponse:
    """가상 보드 대기열에서 여러 종목을 일괄 제외 처리합니다.

    Args:
        request (BatchIgnoreRequest): 일괄 제외할 종목들의 티커 목록을 포함하는 요청 바디.

    Returns:
        dict: ``{"status": "success", "message": str}`` 또는 400/500 오류 응답.
    """
    try:
        success = await command_service.batch_ignore_stocks("virtual_신규상장주", request.tickers)
        if success:
            return {"status": "success", "message": f"성공적으로 {len(request.tickers)}개 종목이 일괄 제외되었습니다."}
        return JSONResponse(status_code=400, content={"message": "일괄 제외 처리에 실패했습니다."})
    except Exception as e:
        logger.error(f"Error executing batch ignore for virtual board: {str(e)}")
        return JSONResponse(status_code=500, content={"message": f"서버 내부 오류: {str(e)}"})
