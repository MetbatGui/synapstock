"""플랫 도메인 모델 개편에 따른 API 라우터 하방 호환성 및 서비스 결합 통합 테스트 (모킹 배제)."""

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from synapstock.presentation.web.routes.board_routes import router


@pytest.fixture
def api_client(integration_test_env):
    """실제 통합 환경(임시 디스크 및 의존성 컨테이너가 갱신된 환경)이 주입된 FastAPI TestClient."""
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestApiFlatIntegration:
    """모킹을 배제하고 라우터-서비스-레포지토리-디스크까지의 결합 상태를 검증하는 통합 테스트."""

    def test_get_board_data_returns_legacy_tree_format(self, api_client, integration_test_env):
        """백엔드 도메인은 플랫 맵이지만, /api/board GET 요청은 프론트엔드 호환성을 위해 트리 구조 형태로 역직렬화(마샬링)되어 반환되어야 한다."""
        # 1. 테스트용 구형 트리 JSON 보드 파일을 임시 디렉터리 내에 물리적으로 생성
        legacy_data = {
            "name": "테스트테마",
            "root": {
                "name": "테스트테마",
                "depth": 0,
                "nodes": [
                    {
                        "name": "하위섹터1",
                        "depth": 1,
                        "nodes": [],
                        "stocks": [
                            {"name": "삼성전자", "ticker": "005930"}
                        ]
                    }
                ],
                "stocks": []
            }
        }
        
        # integration_test_env fixture에서 지정한 임시 데이터 디렉터리 하위의 board 폴더 경로 확보
        temp_data_dir = integration_test_env
        board_file = temp_data_dir / "board" / "theme_test_board.json"
        board_file.write_text(json.dumps(legacy_data, ensure_ascii=False), encoding="utf-8")

        # 2. API 요청 수행
        response = api_client.get("/api/board?name=theme_test_board")
        
        assert response.status_code == 200
        res_json = response.json()
        
        # 3. 반환 포맷 검증 (트리 형태가 제대로 유지되는지 확인)
        assert res_json["name"] == "테스트테마"
        
        # 루트 노드 바로 아래 stocks는 비어있어야 함
        assert res_json["stocks"] == []
        
        # 1depth 자식 노드 확인
        assert len(res_json["nodes"]) == 1
        child_node = res_json["nodes"][0]
        assert child_node["name"] == "하위섹터1"
        assert "nodes" in child_node
        assert len(child_node["stocks"]) == 1
        assert child_node["stocks"][0]["ticker"] == "005930"

    def test_add_stock_api_writes_new_flat_format_to_disk(self, api_client, integration_test_env):
        """/api/stock/add API 요청 시 비즈니스 연산 완료 후, 디스크에는 신형 플랫 포맷 JSON으로 저장되어야 한다."""
        # 1. 빈 보드 생성 (기존 API 호출)
        create_res = api_client.post("/api/board/create?name=theme_battery")
        assert create_res.status_code == 200
        
        # 2. 노드 추가 (기존 API 호출)
        add_node_res = api_client.post("/api/node/add?board=theme_battery&parent=theme_battery&name=양극재")
        assert add_node_res.status_code == 200

        # 3. 주식 추가 API 호출
        add_stock_res = api_client.post(
            "/api/stock/add?board=theme_battery&parent=theme_battery/양극재&name=에코프로&ticker=086520"
        )
        assert add_stock_res.status_code == 200

        # 4. 물리 디스크의 파일을 직접 열어서 플랫 JSON 구조인지 확인 (모킹 자제 검증)
        temp_data_dir = integration_test_env
        board_file = temp_data_dir / "board" / "theme_battery.json"
        assert board_file.exists()
        
        file_json = json.loads(board_file.read_text(encoding="utf-8"))
        
        # 디스크에는 플랫 포맷으로 쓰였는지 검증
        assert "nodes" in file_json
        assert "theme_battery" in file_json["nodes"]
        assert "theme_battery/양극재" in file_json["nodes"]
        
        # 주식이 올바른 노드 아래에 적재되었는지 확인
        target_node = file_json["nodes"]["theme_battery/양극재"]
        assert len(target_node["stocks"]) == 1
        assert target_node["stocks"][0]["ticker"] == "086520"
        
        # API 조회 시에는 구형 트리 구조로 나와야 함
        get_res = api_client.get("/api/board?name=theme_battery")
        assert get_res.status_code == 200
        get_json = get_res.json()
        assert get_json["nodes"][0]["name"] == "양극재"
        assert get_json["nodes"][0]["stocks"][0]["ticker"] == "086520"
