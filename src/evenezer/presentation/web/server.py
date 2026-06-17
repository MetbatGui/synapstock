"""FastAPI 서버 진입점.

앱 초기화, 라우터 등록, 정적 파일 마운트, WebSocket, 시작 이벤트 등
서버 레벨의 인프라륜쪫만 담당하며 비증니스 로직은 routes/ 하위 모듈에 완전 위임합니다.
"""

import asyncio
import contextlib
import logging
import os
import threading
from pathlib import Path

# 애플리케이션 전체 기본 로깅 설정 (FastAPI 콘솔 출력용)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from evenezer.presentation.web.core.dependencies import sync_indices_if_needed
from evenezer.presentation.web.core.websocket_manager import manager
from evenezer.presentation.web.routes import (
    board_routes,
    financial_routes,
    report_routes,
    statistics_routes,
    stock_routes,
    heatmap_routes,
)

# 강한 참조 유지를 위한 글로벌 백그라운드 태스크 세트
background_tasks = set()


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # ── 시작 시점 ─────────────────────────────────────────────────────────────
    logger.info("[Lifespan] Evenezer 서버 시작 중...")
    
    # 1. DI 컨테이너 백그라운드 스레드 및 워커 명시적 기동
    from evenezer.infrastructure.container import container
    container.start_background_services()

    # 2. 인덱스 동기화 프로세스 시작 (Google Drive)
    logger.info("[Lifespan] 인덱스 동기화 프로세스 시작 (Google Drive)")
    from evenezer.presentation.web.core.dependencies import (
        sync_news_archive,
        sync_all_new_listings_if_needed,
    )

    async def run_sync_sequentially():
        try:
            await sync_indices_if_needed(force=True)
            await sync_news_archive()
            await sync_all_new_listings_if_needed()
        except Exception as e:
            logger.error(f"[Lifespan] 백그라운드 동기화 중 오류 발생: {e}")

    task = asyncio.create_task(run_sync_sequentially())
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)

    logger.info("[Lifespan] 서버 초기화 완료 (동기화는 백그라운드에서 진행 중).")
    
    yield
    
    # ── 종료 시점 ─────────────────────────────────────────────────────────────
    logger.info("[Lifespan] Evenezer 서버 종료 중...")
    
    # 1. 실행 중인 백그라운드 태스크 취소 및 대기
    if background_tasks:
        logger.info(f"[Lifespan] 실행 중인 백그라운드 태스크 {len(background_tasks)}개 취소 처리 중...")
        for t in background_tasks:
            t.cancel()
        await asyncio.gather(*background_tasks, return_exceptions=True)
        background_tasks.clear()
        
    # 2. 컨테이너 서비스 리소스 해제
    await container.close_services()
    logger.info("[Lifespan] 서버 종료 프로세스 완료.")


# ── 앱 생성 ─────────────────────────────────────────────────────────────────
app = FastAPI(lifespan=lifespan)

# ── 정적 파일 마운트 ─────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(BASE_DIR, "static")
os.makedirs(static_dir, exist_ok=True)

templates = Jinja2Templates(directory=static_dir)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

pdf_dir = Path("data/pdf")
pdf_dir.mkdir(parents=True, exist_ok=True)
app.mount("/pdf", StaticFiles(directory=str(pdf_dir)), name="pdf")

report_dir = Path("data/report")
report_dir.mkdir(parents=True, exist_ok=True)

# ── 라우터 등록 ──────────────────────────────────────────────────────────────
app.include_router(board_routes.router)
app.include_router(stock_routes.router)
app.include_router(report_routes.router)
app.include_router(statistics_routes.router)
app.include_router(financial_routes.router)
app.include_router(heatmap_routes.router)


# ── 페이지 라우트 ────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def get_main_app(request: Request):
    """메인 통합 웹 애플리케이션 페이지를 서빙합니다.

    Args:
        request (Request): FastAPI Request 객체.

    Returns:
        HTMLResponse: ``index.html`` 템플릿 응답.
    """
    return templates.TemplateResponse("index.html", {"request": request, "ticker": None, "mode": "main"})


@app.get("/stock/{ticker}", response_class=HTMLResponse)
async def get_stock_dashboard(request: Request, ticker: str):
    """개별 종목 대시보드 페이지를 서빙합니다.

    Args:
        request (Request): FastAPI Request 객체.
        ticker (str): URL 경로에 포함된 종목 티커 심볼.

    Returns:
        HTMLResponse: ``index.html`` 템플릿 응답.
    """
    return templates.TemplateResponse("index.html", {"request": request, "ticker": ticker, "mode": "dashboard"})


@app.get("/statistics", response_class=HTMLResponse)
async def get_statistics_page(request: Request):
    """수급 통계 분석 페이지 기본 진입점을 서빙합니다."""
    return templates.TemplateResponse("index.html", {"request": request, "ticker": None, "mode": "statistics"})


@app.get("/heatmap", response_class=HTMLResponse)
async def get_heatmap_page(request: Request):
    """테마 히트맵 분석 최상위 탭 페이지를 서빙합니다."""
    return templates.TemplateResponse("index.html", {"request": request, "ticker": None, "mode": "heatmap"})


@app.get("/statistics/{subpath:path}", response_class=HTMLResponse)
async def get_statistics_subpage(request: Request, subpath: str):
    """수급 분석 서브 라우트(netbuy/ranking 등)를 위해 SPA 템플릿을 서빙합니다."""
    return templates.TemplateResponse(
        "index.html", {"request": request, "ticker": None, "mode": f"statistics-{subpath.replace('/', '-')}"}
    )


# ── WebSocket ────────────────────────────────────────────────────────────────
@app.websocket("/ws/logs")
async def websocket_endpoint(websocket: WebSocket):
    """실시간 로그 스트리밍을 위한 WebSocket 연결을 처리합니다.

    연결된 클라이언트를 ``manager`` 싱글턴에 등록하고,
    연결이 끊쳤(``WebSocketDisconnect``) 데 자동으로 제거합니다.

    Args:
        websocket (WebSocket): FastAPI WebSocket 연결 객체.
    """
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ── 서버 시작/종료 이벤트 (lifespan에서 통합 관리) ─────────────────────────────


# ── 실행 헬퍼 ────────────────────────────────────────────────────────────────
def run_server(port: int = 8090):
    """Uvicorn 서버를 실행합니다.

    보안을 위해 기본적으로 로컬호스트(``127.0.0.1``)에 바인딩하며 언급된 포트로 서버를 구동합니다.
    환경 변수 ``EVENEZER_HOST``가 지정되면 해당 호스트에 바인딩합니다.

    Args:
        port (int): 리스닝할 TCP 포트 번호. 기본값은 ``8090``.
    """
    host = os.environ.get("EVENEZER_HOST", "127.0.0.1")
    uvicorn.run(app, host=host, port=port, log_level="info")


def start_web_server_background(port: int = 8090):
    """서버를 백그라운드 데몬 스레드에서 시작하고 스레드 객체를 반환합니다.

    GUI/런처에서 비동기적으로 서버를 시작할 때 사용합니다.

    Args:
        port (int): 리스닝할 TCP 포트 번호. 기본값은 ``8090``.

    Returns:
        threading.Thread: 시작된 백그라운드 스레드 객체.
    """
    thread = threading.Thread(target=run_server, args=(port,), daemon=True)
    thread.start()
    return thread


if __name__ == "__main__":
    run_server()
