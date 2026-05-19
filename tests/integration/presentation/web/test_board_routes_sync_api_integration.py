from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from synapstock.presentation.web.server import app


class TestBoardRoutesSyncApiIntegration:
    """웹 API 라우터(/api/board/virtual/sync) 호출 시 구글 드라이브 동기화가 안전하게 격발되는지 웹 통합 테스트."""

    @pytest.fixture
    def client(self):
        """FastAPI 테스트 클라이언트를 준비합니다."""
        return TestClient(app)

    def test_sync_virtual_boards_api_success_flow(self, client):
        """API 호출 시 동기화 서비스가 호출되며 200 OK와 성공 리포트 응답을 주는지 검증."""
        # dependencies 모듈의 board_file_sync_service.sync_with_drive를 모의(Mock)합니다.
        mock_sync_fn = AsyncMock(return_value=True)

        with patch(
            "synapstock.presentation.web.routes.board_routes.board_file_sync_service.sync_with_drive",
            mock_sync_fn
        ):
            response = client.post("/api/board/virtual/sync")

            # 검증 A: 상태 코드가 200 OK 인지 검증
            assert response.status_code == 200

            # 검증 B: 반환된 JSON 리포트 확인
            res_json = response.json()
            assert res_json["status"] == "success"
            assert "양방향 동기화가 무사히 완료되었습니다" in res_json["message"]

            # 검증 C: 실제 동기화 비즈니스 엔진이 정상적으로 격발되었는지 무결성 검증
            mock_sync_fn.assert_called_once()

    def test_sync_virtual_boards_api_failure_flow(self, client):
        """동기화 서비스 실패 시 500 에러와 명확한 오류 리포트를 주는지 검증."""
        mock_sync_fn = AsyncMock(return_value=False)

        with patch(
            "synapstock.presentation.web.routes.board_routes.board_file_sync_service.sync_with_drive",
            mock_sync_fn
        ):
            response = client.post("/api/board/virtual/sync")

            # 검증 A: 500 Internal Server Error 상태 코드 검증
            assert response.status_code == 500

            # 검증 B: 반환된 에러 JSON 메시지 확인
            res_json = response.json()
            assert "실패했습니다" in res_json["message"]

            # 검증 C: 격발 호출 보장
            mock_sync_fn.assert_called_once()
