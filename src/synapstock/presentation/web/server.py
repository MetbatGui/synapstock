from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
import os
import threading
import json
import asyncio
from typing import List
from pathlib import Path

# 도메인 서비스 임포트
from synapstock.services.board_service import BoardService
from synapstock.adapters.local.board_repo import LocalBoardRepository
from synapstock.adapters.miro.miro_mindmap import MiroMindmapAdapter
from synapstock.adapters.disclosure.disclosure_adapter import DartDisclosureAdapter

app = FastAPI()

# 디렉토리 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(BASE_DIR, "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir)

templates = Jinja2Templates(directory=static_dir)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# PDF 리포트 파일 서빙을 위한 정적 경로 추가
pdf_dir = Path("data/pdf")
pdf_dir.mkdir(parents=True, exist_ok=True)
app.mount("/pdf", StaticFiles(directory=str(pdf_dir)), name="pdf")

# 전역 서비스 레이어 초기화 (싱글톤 패턴 형태)
repo = LocalBoardRepository(Path("data") / "board")
miro_adapter = MiroMindmapAdapter(os.getenv("MIRO_ACCESS_TOKEN", ""))
disclosure_adapter = DartDisclosureAdapter()
service = BoardService(repo, miro_adapter, disclosure_adapter)

# WebSocket 연결 관리자
class ConnectionManager:
    """실시간 로그 브로드캐스팅을 위한 WebSocket 연결을 관리합니다."""
    def __init__(self):
        """활성 연결 목록을 빈 리스트로 초기화합니다."""
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """새로운 WebSocket 연결을 수락하고 활성 풀에 추가합니다.
        
        Args:
            websocket: 추가할 WebSocket 연결 객체.
        """
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        """활성 풀에서 WebSocket 연결을 제거합니다.
        
        Args:
            websocket: 제거할 WebSocket 연결 객체.
        """
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        """모든 활성 WebSocket 연결에 메시지를 브로드캐스트합니다.
        
        Args:
            message: 브로드캐스트할 JSON 문자열 메시지.
        """
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

@app.get("/stock/{ticker}", response_class=HTMLResponse)
async def get_stock_dashboard(request: Request, ticker: str):
    """개별 종목 대시보드 페이지를 서빙합니다.
    
    Args:
        request: FastAPI 요청 객체.
        ticker: 종목 티커 심볼.
        
    Returns:
        TemplateResponse: 대시보드 모드로 렌더링된 index.html.
    """
    return templates.TemplateResponse("index.html", {"request": request, "ticker": ticker, "mode": "dashboard"})

@app.get("/", response_class=HTMLResponse)
async def get_main_app(request: Request):
    """메인 통합 웹 애플리케이션 페이지를 서빙합니다.
    
    Args:
        request: FastAPI 요청 객체.
        
    Returns:
        TemplateResponse: 메인 모드로 렌더링된 index.html.
    """
    return templates.TemplateResponse("index.html", {"request": request, "ticker": None, "mode": "main"})

@app.get("/api/boards")
async def get_boards():
    """사용 가능한 마인드맵 보드 목록을 반환합니다.
    
    Returns:
        List[str]: 보드 이름 목록.
    """
    return service.list_boards()

@app.get("/api/board")
async def get_board_data(name: str):
    """특정 보드의 계층형 데이터를 반환합니다.
    
    Args:
        name: 불러올 보드의 이름.
        
    Returns:
        dict: 트리 렌더링을 위해 구조화된 보드 데이터.
        JSONResponse: 보드 로딩 실패 시 404 에러.
    """
    try:
        board = service.load_board(name)
        # pydantic/dataclass 모델을 dict로 변환 (순환 참조 주의)
        def to_dict(node):
            return {
                "name": node.name,
                "nodes": [to_dict(n) for n in node.nodes],
                "stocks": [{"name": s.name, "ticker": s.ticker, "reports": s.reports} for s in node.stocks]
            }
        return to_dict(board.root)
    except Exception as e:
        return JSONResponse(status_code=404, content={"message": str(e)})

@app.get("/api/disclosure/{ticker}")
async def get_disclosures(ticker: str):
    """특정 종목의 최근 공시 목록을 반환합니다.
    
    Args:
        ticker: 종목 티커 심볼.
        
    Returns:
        List[dict]: 공시 항목 목록.
        JSONResponse: 조회 실패 시 500 에러.
    """
    try:
        # ticker가 'none'이거나 비어있으면 빈 리스트 반환
        if not ticker or ticker == 'none':
            return []
        disclosures = service.get_disclosures(ticker)
        return disclosures
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})

@app.get("/api/stock/info/{ticker}")
async def get_stock_info(ticker: str):
    """티커를 기반으로 종목명 등의 기본 정보를 반환합니다.
    
    모든 로컬 보드를 검색하여 일치하는 티커를 찾습니다.
    
    Args:
        ticker: 종목 티커 심볼.
        
    Returns:
        dict: 티커와 찾은 종목명을 포함하는 객체.
        JSONResponse: 검색 실패 시 500 에러.
    """
    try:
        boards = service.list_boards()
        for b_name in boards:
            board = service.load_board(b_name)
            
            # 재귀적으로 종목 찾기
            def find_stock_recursive(node):
                # 1. 현재 노드의 stocks 확인
                if hasattr(node, 'stocks') and node.stocks:
                    for s in node.stocks:
                        if s.ticker == ticker:
                            return s.name
                
                # 2. 자식 노드들 탐색
                if hasattr(node, 'nodes') and node.nodes:
                    for n in node.nodes:
                        res = find_stock_recursive(n)
                        if res: return res
                return None
            
            # Pydantic 모델인 경우 .root 접근, 아니면 직접 탐색
            root_node = getattr(board, 'root', board)
            name = find_stock_recursive(root_node)
            
            if name:
                return {"ticker": ticker, "name": name}
        
        return {"ticker": ticker, "name": None}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"message": str(e)})

@app.post("/api/sync")
async def trigger_sync(name: str):
    """백그라운드에서 Miro 동기화를 트리거합니다.
    
    활성 WebSocket 연결을 통해 진행 로그를 브로드캐스트합니다.
    
    Args:
        name: 동기화할 보드의 이름.
        
    Returns:
        dict: 동기화가 시작되었음을 나타내는 상태.
    """
    def do_sync():
        async def log_callback(msg, val):
            await manager.broadcast(json.dumps({"type": "log", "message": msg, "progress": val}))
        
        try:
            # 실제 동기화 호출
            board = service.load_board(name)
            # 비동기 통신을 위해 loop 획득
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            def sync_progress(m, v):
                loop.run_until_complete(log_callback(m, v))
                
            service.sync_with_miro(board, progress_callback=sync_progress)
        except Exception as e:
            # 에러 발생 시 로그 전송
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(log_callback(f"Error: {str(e)}", 0))
    
    thread = threading.Thread(target=do_sync, daemon=True)
    thread.start()
    return {"status": "started"}

@app.post("/api/node/add")
async def add_node(board: str, parent: str, name: str):
    """지정된 부모 노드 아래에 새 노드를 추가합니다.
    
    Args:
        board: 대상 보드 이름.
        parent: 부모 노드의 이름.
        name: 추가할 새 노드의 이름.
        
    Returns:
        dict: 성공 상태.
        JSONResponse: 부모 노드를 찾을 수 없는 경우 404.
    """
    success = service.add_node(board, parent, name)
    if success:
        return {"status": "success"}
    return JSONResponse(status_code=404, content={"message": "Parent node not found"})

@app.post("/api/stock/add")
async def add_stock(board: str, parent: str, name: str, ticker: str):
    """지정된 부모 노드 아래에 새 종목을 추가합니다.
    
    Args:
        board: 대상 보드 이름.
        parent: 부모 노드의 이름.
        name: 종목명.
        ticker: 종목 티커 심볼.
        
    Returns:
        dict: 성공 상태.
        JSONResponse: 부모 노드를 찾을 수 없는 경우 404.
    """
    success = service.add_stock(board, parent, name, ticker)
    if success:
        return {"status": "success"}
    return JSONResponse(status_code=404, content={"message": "Parent node not found"})

@app.delete("/api/stock/delete")
async def delete_stock(board: str, ticker: str):
    """보드에서 종목을 삭제합니다.
    
    Args:
        board: 대상 보드 이름.
        ticker: 삭제할 종목의 티커 심볼.
        
    Returns:
        dict: 성공 상태.
        JSONResponse: 삭제 실패 시 404 (종목을 찾을 수 없는 경우).
    """
    success = service.delete_stock(board, ticker)
    if success:
        return {"status": "success"}
    return JSONResponse(status_code=404, content={"message": "Stock not found in board"})

@app.delete("/api/node/delete")
async def delete_node(board: str, name: str):
    """노드를 삭제하고 그 자식들을 부모 노드에 재연결합니다.
    
    Args:
        board: 대상 보드 이름.
        name: 삭제할 노드의 이름.
        
    Returns:
        dict: 성공 상태.
        JSONResponse: 삭제 실패 시 400 (루트 노드이거나 없는 경우).
    """
    success = service.delete_node(board, name)
    if success:
        return {"status": "success"}
    return JSONResponse(status_code=400, content={"message": "Delete failed (Root cannot be deleted or node not found)"})

@app.get("/api/stock/search")
async def search_stock(q: str):
    """네이버 증권 자동완성 API를 프록시합니다.
    
    Args:
        q: 검색어.
        
    Returns:
        List[dict]: 네이버에서 가져온 검색 결과.
    """
    results = service.search_ticker(q)
    return results

@app.websocket("/ws/logs")
async def websocket_endpoint(websocket: WebSocket):
    """실시간 로그 스트리밍을 위한 WebSocket 연결을 처리합니다.
    
    Args:
        websocket: WebSocket 연결 객체.
    """
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

def run_server(port: int = 8090):
    """Uvicorn을 사용하여 FastAPI 서버를 실행합니다.
    
    Args:
        port: 수신 대기할 포트 번호. 기본값은 8090.
    """
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

def start_web_server_background(port: int = 8090):
    """백그라운드 데몬 스레드에서 FastAPI 서버를 시작합니다.
    
    Args:
        port: 수신 대기할 포트 번호. 기본값은 8090.
        
    Returns:
        threading.Thread: 서버를 실행 중인 스레드 객체.
    """
    thread = threading.Thread(target=run_server, args=(port,), daemon=True)
    thread.start()
    return thread

if __name__ == "__main__":
    run_server()
