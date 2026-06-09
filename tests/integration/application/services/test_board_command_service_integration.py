import shutil
from pathlib import Path

import pytest

from synapstock.application.services.board_file_sync_service import BoardFileSyncService
from synapstock.application.services.command_service import BoardCommandService
from synapstock.infrastructure.adapters.local.board_repo import LocalBoardRepository


class TestBoardCommandServiceIntegration:
    """BoardCommandService와 실제 파일시스템 레포지토리, 동기화 서비스 간의 물리 통합 테스트."""

    @pytest.fixture(autouse=True)
    def setup_sandbox(self, tmp_path: Path):
        """테스트마다 격리된 임시 디렉토리를 생성하여 실물 인프라 어댑터들을 초기화합니다."""
        self.test_dir = tmp_path / "data_board"
        self.test_dir.mkdir(parents=True, exist_ok=True)

        # 실물 레포지토리 초기화
        self.repository = LocalBoardRepository(self.test_dir)

        # 실물 동기화 서비스 초기화 (구글 드라이브 통신은 비워두고, 로컬 매니페스트 I/O만 실계측)
        self.manifest_path = self.test_dir / "board_sync_manifest.json"
        self.sync_service = BoardFileSyncService(
            repository=self.repository,
            drive_adapter=None,
            theme_folder_id=None,
            manifest_path=self.manifest_path
        )

        # 실물 보드 명령 서비스 조립 (동기화 훅 연동!)
        self.service = BoardCommandService(repository=self.repository, sync_service=self.sync_service)

        yield  # 🌟 테스트 실행

        # Teardown: 임시 디렉토리 완전 삭제
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    @pytest.mark.asyncio
    async def test_board_creation_and_node_modification_physical_flow(self):
        """보드 생성 및 노드/종목 변경 시 물리 파일시스템과 매니페스트의 갱신 라이프사이클을 실계측 검증."""
        board_id = "virtual_test_integration"

        # --- PHASE 1: 물리 보드 생성 ---
        success = self.service.create_board(board_id)
        assert success is True

        # 검증 A: 디스크 상에 실제 {board_id}.json 물리 파일이 써졌는지 검증
        board_file = self.test_dir / f"{board_id}.json"
        assert board_file.exists() is True

        # 검증 B: 디스크 상에 board_sync_manifest.json 물리 매니페스트가 생성되었고 보드가 편입되었는지 검증
        assert self.manifest_path.exists() is True
        manifest_data = self.sync_service.load_local_manifest()
        assert board_id in manifest_data["boards"]
        assert manifest_data["boards"][board_id]["deleted"] is False

        # --- PHASE 2: 노드 추가 및 매니페스트 시간 갱신 검증 ---
        # 최초 생성 시 기록된 최종 수정 시각 획득
        initial_modified = manifest_data["boards"][board_id]["last_modified"]

        # 물리 노드 추가 명령 실행
        success = self.service.add_node(board_id, board_id, "인프라노드")
        assert success is True

        # 검증 C: 수정 직후 매니페스트 상의 수정 타임스탬프가 실제로 더 최신으로 갱신되었는지 검증
        updated_manifest = self.sync_service.load_local_manifest()
        updated_modified = updated_manifest["boards"][board_id]["last_modified"]
        assert updated_modified > initial_modified

        # --- PHASE 3: 종목 추가 및 물리 보드 파싱 검증 ---
        success = await self.service.add_stock(board_id, "인프라노드", "삼성전자", "005930")
        assert success is True

        # 검증 D: 디스크 상의 JSON을 직접 열어서 종목 정보가 안전하게 영속화되었는지 무결성 검증
        board = self.repository.load(board_id)
        stock = board.find_stock("005930")
        assert stock is not None
        assert stock.name == "삼성전자"

        # --- PHASE 4: 보드 물리적 삭제 및 deleted=True 매니페스트 영속화 검증 ---
        success = self.service.delete_board(board_id)
        assert success is True

        # 검증 E: 디스크 상에서 {board_id}.json 파일이 물리적으로 삭제되어 소멸되었는지 검증
        assert board_file.exists() is False

        # 검증 F: 매니페스트 물리 파일 내에 deleted=True 마킹이 확실하게 영속화되었는지 검증
        final_manifest = self.sync_service.load_local_manifest()
        assert board_id in final_manifest["boards"]
        assert final_manifest["boards"][board_id]["deleted"] is True
