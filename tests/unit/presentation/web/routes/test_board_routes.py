import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

from evenezer.presentation.web.routes.board_routes import router
from evenezer.domain.models import Stock

app = FastAPI()
app.include_router(router)

client = TestClient(app)


@pytest.fixture
def mock_deps():
    with patch("evenezer.presentation.web.routes.board_routes.query_service") as mock_query, \
         patch("evenezer.presentation.web.routes.board_routes.command_service") as mock_command:
        yield mock_query, mock_command


def test_add_stock_success_no_duplicate(mock_deps):
    """중복 종목이 존재하지 않을 때, 정상적으로 종목 추가가 실행되는지 검증."""
    mock_query, mock_command = mock_deps
    mock_query.get_stock_by_ticker.return_value = None
    mock_command.add_stock = AsyncMock(return_value=True)

    response = client.post("/api/stock/add?board=theme_semiconductor&parent=대장주&name=삼성전자&ticker=005930")

    assert response.status_code == 200
    assert response.json() == {"status": "success"}
    mock_query.get_stock_by_ticker.assert_called_once_with("005930")
    mock_command.add_stock.assert_called_once_with("theme_semiconductor", "대장주", "삼성전자", "005930")


def test_add_stock_fails_when_duplicate_in_other_theme_board(mock_deps):
    """다른 테마 보드에 중복 종목이 이미 존재할 경우 409 Conflict를 반환하고 추가를 차단하는지 검증."""
    mock_query, mock_command = mock_deps
    
    # 중복 종목 모의 정보 설정 (티커 005930이 이미 theme_battery 보드의 [배터리, 양극재] 노드에 존재함)
    mock_stock = Stock(name="삼성전자", ticker="005930")
    mock_query.get_stock_by_ticker.return_value = (mock_stock, "theme_battery", ["배터리", "양극재"])
    
    # 실제 보드 이름 조회를 위해 load_board 모킹
    mock_board = MagicMock()
    mock_board.name = "이차전지 테마"
    mock_query.load_board.return_value = mock_board

    response = client.post("/api/stock/add?board=theme_semiconductor&parent=대장주&name=삼성전자&ticker=005930")

    assert response.status_code == 409
    data = response.json()
    assert data["status"] == "duplicate"
    assert "이미 '삼성전자(005930)' 종목이 [이차전지 테마] > 배터리 > 양극재 에 존재하므로 추가할 수 없습니다." in data["message"]
    
    # command_service.add_stock이 호출되지 않았어야 함 (원천 차단)
    mock_command.add_stock.assert_not_called()


def test_add_stock_bypasses_duplicate_check_for_virtual_board_source(mock_deps):
    """이미 기등록된 보드가 가상보드(virtual_신규상장주)인 경우, 중복 검사를 우회하여 추가하는지 검증."""
    mock_query, mock_command = mock_deps
    
    # 중복 검사 결과가 가상보드로 나옴
    mock_stock = Stock(name="삼성전자", ticker="005930")
    mock_query.get_stock_by_ticker.return_value = (mock_stock, "virtual_신규상장주", ["2025년"])
    mock_command.add_stock = AsyncMock(return_value=True)

    response = client.post("/api/stock/add?board=theme_semiconductor&parent=대장주&name=삼성전자&ticker=005930")

    assert response.status_code == 200
    assert response.json() == {"status": "success"}
    mock_command.add_stock.assert_called_once()


def test_add_stock_bypasses_duplicate_check_for_virtual_board_target(mock_deps):
    """추가하려는 대상 보드가 가상보드(virtual_신규상장주)인 경우, 중복 검사를 우회하여 추가하는지 검증."""
    mock_query, mock_command = mock_deps
    
    # 중복 검사 결과 다른 일반 테마 보드에 이미 존재하지만, 대상 보드가 가상보드임
    mock_stock = Stock(name="삼성전자", ticker="005930")
    mock_query.get_stock_by_ticker.return_value = (mock_stock, "theme_semiconductor", ["반도체", "대장주"])
    mock_command.add_stock = AsyncMock(return_value=True)

    response = client.post("/api/stock/add?board=virtual_신규상장주&parent=2025년&name=삼성전자&ticker=005930")

    assert response.status_code == 200
    assert response.json() == {"status": "success"}
    mock_command.add_stock.assert_called_once()
