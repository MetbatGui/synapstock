"""플랫 도메인 모델을 지탱하는 LocalBoardRepository 호환 및 결합 테스트."""

import json
from pathlib import Path

import pytest

from evenezer.domain.models import Board, Stock
from evenezer.infrastructure.adapters.local.board_repo import LocalBoardRepository


@pytest.fixture
def repo(tmp_path):
    """임시 디렉터리 기반의 로컬 저장소 어댑터 (모킹 없음)."""
    return LocalBoardRepository(root_dir=tmp_path)


class TestLocalBoardRepositoryFlat:
    """레거시 트리 포맷 호환 및 신형 플랫 포맷 파일 입출력 결합 테스트 (모킹 자제)."""

    def test_load_legacy_tree_json_migration(self, repo, tmp_path):
        """기존의 구형 트리 구조 JSON 파일을 로드했을 때, 플랫 맵 구조(dict[path, Node])로 자동 격상(마이그레이션)되어야 한다."""
        legacy_data = {
            "name": "Theme_반도체",
            "root": {
                "name": "Theme_반도체",
                "depth": 0,
                "nodes": [
                    {
                        "name": "디바이스",
                        "depth": 1,
                        "nodes": [],
                        "stocks": [
                            {"name": "리노공업", "ticker": "058470"}
                        ]
                    },
                    {
                        "name": "소재",
                        "depth": 1,
                        "nodes": [
                            {
                                "name": "포토레지스트",
                                "depth": 2,
                                "nodes": [],
                                "stocks": [
                                    {"name": "동진쎄미켐", "ticker": "005290"}
                                ]
                            }
                        ],
                        "stocks": []
                    }
                ],
                "stocks": []
            }
        }

        # 물리적인 JSON 파일 직접 생성 (구형 트리 데이터 형태)
        board_file = tmp_path / "Theme_반도체.json"
        board_file.write_text(json.dumps(legacy_data, ensure_ascii=False), encoding="utf-8")

        # Act: 레포지토리를 통해 로드
        board = repo.load("Theme_반도체")

        # Assert: 도메인 모델이 플랫 맵 구조로 적절히 격상되어야 함
        assert board.name == "Theme_반도체"
        
        # 1. 딕셔너리에 노드 개수가 4개 (루트, 디바이스, 소재, 포토레지스트) 여야 함
        assert len(board.nodes) == 4
        
        # 2. 루트 노드 확인
        assert "Theme_반도체" in board.nodes
        assert board.nodes["Theme_반도체"].depth == 0
        assert board.nodes["Theme_반도체"].parent_path is None
        
        # 3. 디바이스 노드 확인 및 주식 유무
        assert "Theme_반도체/디바이스" in board.nodes
        device_node = board.nodes["Theme_반도체/디바이스"]
        assert device_node.depth == 1
        assert device_node.parent_path == "Theme_반도체"
        assert len(device_node.stocks) == 1
        assert device_node.stocks[0].ticker == "058470"
        
        # 4. 깊은 경로 노드 (포토레지스트) 확인 및 주식 유무
        deep_path = "Theme_반도체/소재/포토레지스트"
        assert deep_path in board.nodes
        photo_node = board.nodes[deep_path]
        assert photo_node.depth == 2
        assert photo_node.parent_path == "Theme_반도체/소재"
        assert len(photo_node.stocks) == 1
        assert photo_node.stocks[0].ticker == "005290"

    def test_save_as_new_flat_format(self, repo, tmp_path):
        """새로 저장된 보드 파일은 플랫 맵 구조를 지닌 JSON 포맷이어야 한다."""
        board = Board(name="Theme_이차전지")
        board.add_node("Theme_이차전지", "소재")
        board.add_stock_to_node("Theme_이차전지/소재", Stock(name="에코프로비엠", ticker="247540"))

        # 저장 집행
        repo.save(board)

        board_file = tmp_path / "Theme_이차전지.json"
        assert board_file.exists()

        # 물리적 파일 내용 검증
        file_content = json.loads(board_file.read_text(encoding="utf-8"))
        
        # 신형 플랫 포맷의 Key 필드들이 존재하는지 검증
        assert "name" in file_content
        assert file_content["name"] == "Theme_이차전지"
        assert "nodes" in file_content
        
        # nodes에 플랫 키 형태로 노드가 적재되었는지 확인
        nodes_dict = file_content["nodes"]
        assert "Theme_이차전지" in nodes_dict
        assert "Theme_이차전지/소재" in nodes_dict
        assert "stocks" in nodes_dict["Theme_이차전지/소재"]
        assert nodes_dict["Theme_이차전지/소재"]["stocks"][0]["ticker"] == "247540"
        
        # 구형 "root" 키는 신형 구조에 없어야 함
        assert "root" not in file_content
