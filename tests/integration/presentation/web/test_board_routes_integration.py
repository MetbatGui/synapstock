import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from fastapi import FastAPI

from evenezer.presentation.web.server import app
from evenezer.domain.models import Board, Node, Stock

client = TestClient(app)


@pytest.fixture
def mock_dependencies():
    with patch("evenezer.presentation.web.routes.board_routes.query_service") as mock_query, \
         patch("evenezer.presentation.web.routes.board_routes.command_service") as mock_command, \
         patch("evenezer.presentation.web.routes.board_routes.media_service") as mock_media, \
         patch("evenezer.presentation.web.routes.board_routes.board_file_sync_service") as mock_file_sync, \
         patch("evenezer.presentation.web.routes.board_routes.sync_service") as mock_miro_sync:
        yield {
            "query": mock_query,
            "command": mock_command,
            "media": mock_media,
            "file_sync": mock_file_sync,
            "miro_sync": mock_miro_sync
        }


def test_get_boards(mock_dependencies):
    """GET /api/boards 엔드포인트 검증."""
    mock_query = mock_dependencies["query"]
    mock_query.get_boards_info.return_value = [{"id": "theme_test", "name": "테스트보드"}]

    response = client.get("/api/boards")

    assert response.status_code == 200
    assert response.json() == [{"id": "theme_test", "name": "테스트보드"}]
    mock_query.get_boards_info.assert_called_once()


def test_get_board_data_normal(mock_dependencies):
    """GET /api/board (일반 보드) 엔드포인트 검증."""
    mock_query = mock_dependencies["query"]
    
    board = Board(id="theme_test", name="테스트보드")
    board.add_node("테스트보드", "하위노드")
    board.add_stock_to_node("테스트보드", Stock(name="삼성전자", ticker="005930"))
    
    mock_query.load_board.return_value = board

    response = client.get("/api/board?name=theme_test")

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "테스트보드"
    assert len(data["nodes"]) == 1
    assert data["nodes"][0]["name"] == "하위노드"
    assert len(data["stocks"]) == 1
    assert data["stocks"][0]["name"] == "삼성전자"
    mock_query.load_board.assert_called_once_with("theme_test")


def test_get_board_data_virtual(mock_dependencies):
    """GET /api/board (가상보드 - 신규상장주) 엔드포인트 검증."""
    mock_query = mock_dependencies["query"]
    
    board = Board(id="virtual_신규상장주", name="신규상장주")
    board.root.stocks.append(Stock(name="종목A", ticker="990011"))
    board.root.stocks.append(Stock(name="종목B", ticker="990016"))
    
    mock_query.load_board.return_value = board

    # 매니페스트 로드 시 발생하는 예외 방지 패치 및 get_board_data 호출
    with patch("builtins.open", MagicMock()), \
         patch("json.loads", return_value={"new_listings": {"990011": {"status": "PENDING"}}}):
        response = client.get("/api/board?name=virtual_신규상장주")

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "신규상장주"
    # 990011은 2025년, 990016은 2026년 가상 노드로 그룹화되어 nodes 하위로 재정렬되어야 함
    assert len(data["nodes"]) == 2
    assert data["nodes"][0]["name"] == "2026년"  # 연도 내림차순 정렬 결과
    assert data["nodes"][1]["name"] == "2025년"
    assert data["nodes"][1]["stocks"][0]["name"] == "종목A"


def test_get_board_data_not_found(mock_dependencies):
    """존재하지 않는 보드 조회 시 404 응답 검증."""
    mock_query = mock_dependencies["query"]
    mock_query.load_board.side_effect = Exception("Board not found")

    response = client.get("/api/board?name=non_existent")

    assert response.status_code == 404
    assert "Board not found" in response.json()["message"]


def test_trigger_sync(mock_dependencies):
    """POST /api/sync 엔드포인트 검증."""
    mock_query = mock_dependencies["query"]
    mock_miro_sync = mock_dependencies["miro_sync"]
    
    mock_query.load_board.return_value = MagicMock()

    # 국소적으로 board_routes 내의 Thread 클래스만 패치하여 스레드 기동을 우회합니다.
    with patch("evenezer.presentation.web.routes.board_routes.threading.Thread") as mock_thread_cls:
        mock_thread_inst = MagicMock()
        mock_thread_cls.return_value = mock_thread_inst
        response = client.post("/api/sync?name=theme_test")

    assert response.status_code == 200
    assert response.json() == {"status": "started"}
    mock_thread_cls.assert_called_once()
    mock_thread_inst.start.assert_called_once()


def test_add_node(mock_dependencies):
    """POST /api/node/add 엔드포인트 검증."""
    mock_command = mock_dependencies["command"]
    
    # 1. 성공 케이스
    mock_command.add_node.return_value = True
    res_success = client.post("/api/node/add?board=theme_test&parent=Root&name=NewNode")
    assert res_success.status_code == 200
    assert res_success.json() == {"status": "success"}

    # 2. 실패 케이스 (404)
    mock_command.add_node.return_value = False
    res_fail = client.post("/api/node/add?board=theme_test&parent=NonExistent&name=NewNode")
    assert res_fail.status_code == 404


def test_delete_node(mock_dependencies):
    """POST /api/node/delete 엔드포인트 검증."""
    mock_command = mock_dependencies["command"]
    
    # 1. 성공 케이스
    mock_command.delete_node.return_value = True
    res_success = client.post("/api/node/delete?board=theme_test&name=TargetNode")
    assert res_success.status_code == 200
    assert res_success.json() == {"status": "success"}

    # 2. 실패 케이스 (400)
    mock_command.delete_node.return_value = False
    res_fail = client.post("/api/node/delete?board=theme_test&name=Root")
    assert res_fail.status_code == 400


def test_add_stock_endpoints(mock_dependencies):
    """POST /api/stock/add 성공/실패(404) 및 중복 차단(409) 엔드포인트 검증."""
    mock_query = mock_dependencies["query"]
    mock_command = mock_dependencies["command"]

    # 1. 중복이 없고 추가 성공인 케이스
    mock_query.get_stock_by_ticker.return_value = None
    mock_command.add_stock = AsyncMock(return_value=True)
    res_ok = client.post("/api/stock/add?board=theme_test&parent=Node&name=Samsung&ticker=005930")
    assert res_ok.status_code == 200
    assert res_ok.json() == {"status": "success"}

    # 2. 추가 실패 케이스 (부모 노드 없음 등 404)
    mock_command.add_stock = AsyncMock(return_value=False)
    res_fail = client.post("/api/stock/add?board=theme_test&parent=NonExistent&name=Samsung&ticker=005930")
    assert res_fail.status_code == 404

    # 3. 다른 보드 중복으로 인한 차단 케이스 (409)
    mock_stock = Stock(name="삼성전자", ticker="005930")
    mock_query.get_stock_by_ticker.return_value = (mock_stock, "theme_other", ["반도체", "대장주"])
    
    mock_other_board = MagicMock()
    mock_other_board.name = "다른 보드"
    mock_query.load_board.return_value = mock_other_board

    res_duplicate = client.post("/api/stock/add?board=theme_test&parent=Node&name=Samsung&ticker=005930")
    assert res_duplicate.status_code == 409
    assert "duplicate" in res_duplicate.json()["status"]


def test_delete_stock(mock_dependencies):
    """DELETE /api/stock/delete 엔드포인트 검증."""
    mock_command = mock_dependencies["command"]
    
    # 1. 성공 케이스
    mock_command.delete_stock = AsyncMock(return_value=True)
    res_success = client.delete("/api/stock/delete?board=theme_test&ticker=005930")
    assert res_success.status_code == 200
    assert res_success.json() == {"status": "success"}

    # 2. 실패 케이스 (404)
    mock_command.delete_stock = AsyncMock(return_value=False)
    res_fail = client.delete("/api/stock/delete?board=theme_test&ticker=005930")
    assert res_fail.status_code == 404





def test_upload_stock_report(mock_dependencies):
    """POST /api/stock/report/upload 엔드포인트 검증."""
    mock_media = mock_dependencies["media"]
    
    # 1. 성공
    mock_media.add_stock_report = AsyncMock(return_value=True)
    res_success = client.post(
        "/api/stock/report/upload?board=theme_test&ticker=005930",
        files={"file": ("test.pdf", b"pdf content", "application/pdf")}
    )
    assert res_success.status_code == 200
    assert res_success.json()["status"] == "success"

    # 2. 잘못된 확장자 (400)
    res_bad_file = client.post(
        "/api/stock/report/upload?board=theme_test&ticker=005930",
        files={"file": ("test.txt", b"text content", "text/plain")}
    )
    assert res_bad_file.status_code == 400

    # 3. 추가 실패 (404)
    mock_media.add_stock_report = AsyncMock(return_value=False)
    res_not_found = client.post(
        "/api/stock/report/upload?board=theme_test&ticker=005930",
        files={"file": ("test.pdf", b"pdf content", "application/pdf")}
    )
    assert res_not_found.status_code == 404


def test_add_stock_report_link(mock_dependencies):
    """POST /api/stock/report/add_link 엔드포인트 검증."""
    mock_media = mock_dependencies["media"]
    
    # 1. 성공
    mock_media.add_stock_report_link = AsyncMock(return_value=True)
    res_success = client.post("/api/stock/report/add_link?board=theme_test&ticker=005930&report_path=path/to")
    assert res_success.status_code == 200
    assert res_success.json() == {"status": "success"}

    # 2. 실패
    mock_media.add_stock_report_link = AsyncMock(return_value=False)
    res_fail = client.post("/api/stock/report/add_link?board=theme_test&ticker=005930&report_path=path/to")
    assert res_fail.status_code == 404


def test_delete_stock_report(mock_dependencies):
    """DELETE /api/stock/report/delete 엔드포인트 검증."""
    mock_media = mock_dependencies["media"]
    
    # 1. 성공
    mock_media.remove_stock_report = AsyncMock(return_value=True)
    res_success = client.delete("/api/stock/report/delete?board=theme_test&ticker=005930&report_path=path/to")
    assert res_success.status_code == 200
    assert res_success.json() == {"status": "success"}

    # 2. 실패
    mock_media.remove_stock_report = AsyncMock(return_value=False)
    res_fail = client.delete("/api/stock/report/delete?board=theme_test&ticker=005930&report_path=path/to")
    assert res_fail.status_code == 404


def test_create_board(mock_dependencies):
    """POST /api/board/create 엔드포인트 검증."""
    mock_command = mock_dependencies["command"]
    
    # 1. 성공
    mock_command.create_board.return_value = True
    res_success = client.post("/api/board/create?name=theme_new")
    assert res_success.status_code == 200
    assert res_success.json() == {"status": "success"}

    # 2. 실패
    mock_command.create_board.return_value = False
    res_fail = client.post("/api/board/create?name=theme_new")
    assert res_fail.status_code == 500


def test_delete_board(mock_dependencies):
    """POST /api/board/delete 엔드포인트 검증."""
    mock_command = mock_dependencies["command"]
    
    # 1. 성공
    mock_command.delete_board.return_value = True
    res_success = client.post("/api/board/delete?name=theme_old")
    assert res_success.status_code == 200
    assert res_success.json() == {"status": "success"}

    # 2. 실패
    mock_command.delete_board.return_value = False
    res_fail = client.post("/api/board/delete?name=theme_old")
    assert res_fail.status_code == 404


def test_sync_virtual_boards(mock_dependencies):
    """POST /api/board/virtual/sync 엔드포인트 검증."""
    mock_file_sync = mock_dependencies["file_sync"]
    
    # 1. 성공
    mock_file_sync.sync_with_drive = AsyncMock(return_value=True)
    res_success = client.post("/api/board/virtual/sync")
    assert res_success.status_code == 200
    assert res_success.json()["status"] == "success"

    # 2. 실패
    mock_file_sync.sync_with_drive = AsyncMock(return_value=False)
    res_fail = client.post("/api/board/virtual/sync")
    assert res_fail.status_code == 500


def test_batch_ignore_virtual_board_stocks(mock_dependencies):
    """POST /api/board/virtual/batch-ignore 엔드포인트 검증."""
    mock_command = mock_dependencies["command"]
    
    # 1. 성공
    mock_command.batch_ignore_stocks = AsyncMock(return_value=True)
    res_success = client.post("/api/board/virtual/batch-ignore", json={"tickers": ["005930", "000660"]})
    assert res_success.status_code == 200
    assert res_success.json()["status"] == "success"

    # 2. 실패
    mock_command.batch_ignore_stocks = AsyncMock(return_value=False)
    res_fail = client.post("/api/board/virtual/batch-ignore", json={"tickers": ["005930"]})
    assert res_fail.status_code == 400
