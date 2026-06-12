import asyncio
import os

import pytest

from synapstock.application.services.board_file_sync_service import BoardFileSyncService
from synapstock.domain.models import Board, Node
from synapstock.infrastructure.adapters.google.google_drive_adapter import GoogleDriveAdapter
from synapstock.infrastructure.adapters.local.board_repo import LocalBoardRepository
from synapstock.infrastructure.config import AppConfig

# secrets/token.json 자격 증명이 실제로 로컬에 존재하는지 조사하여 조건부 스킵 가드 설정
TOKEN_PATH = "secrets/token.json"
token_exists = os.path.exists(TOKEN_PATH)


@pytest.mark.asyncio
@pytest.mark.skipif(not token_exists, reason=" secrets/token.json 파일이 없어 구글 드라이브 통합 테스트를 스킵합니다.")
class TestBoardFileSyncServiceIntegration:
    """실제 구글 드라이브 샌드박스 환경을 활용한 파일 동기화 통합 테스트."""

    @pytest.fixture(autouse=True)
    def setup_sandbox(self):
        """테스트 시작 전에 로컬 저장소와 구글 드라이브에 테스트용 임시 환경을 조성하고, 완료 후 복구합니다."""
        # 1. 설정 로드 및 인프라 조립
        self.config = AppConfig.load()

        # 통합 테스트를 위해 로컬 board 디렉토리를 임시 테스트용 서브 디렉토리로 변경
        self.original_board_dir = self.config.board_dir
        self.test_board_dir = self.config.data_dir / "test_board_sandbox"
        self.test_board_dir.mkdir(parents=True, exist_ok=True)

        # 임시 레포지토리 및 어댑터 초기화
        self.repository = LocalBoardRepository(self.test_board_dir)
        self.drive_adapter = GoogleDriveAdapter(
            token_file=str(self.config.secrets_dir / "token.json"),
            client_secret_file=str(self.config.secrets_dir / "client_secret.json")
        )

        # 1단계에서 일원화한 theme_folder_id 획득
        self.theme_folder_id = self.config.theme_folder_id

        if not self.theme_folder_id:
            pytest.skip("GOOGLE_DRIVE_THEME_FOLDER_ID 환경 변수가 설정되지 않아 통합 테스트를 스킵합니다.")

        # 임시 보드 ID 및 파일명 지정 (가상보드 및 테마보드 1개씩 생성)
        self.test_virtual_id = "virtual_test_sandbox"
        self.test_theme_id = "theme_test_sandbox"
        self.manifest_name = "board_sync_manifest.json"

        self.test_manifest_path = self.test_board_dir / self.manifest_name

        # 임시 보드 도메인 객체 생성
        self.test_board_virtual = Board(
            id=self.test_virtual_id,
            name="test_sandbox",
            root=Node(name="test_sandbox", depth=0)
        )
        self.test_board_theme = Board(
            id=self.test_theme_id,
            name="test_theme_sandbox",
            root=Node(name="test_theme_sandbox", depth=0)
        )

        # 임시 매니페스트 레포지토리 초기화
        from synapstock.infrastructure.adapters.local.board_repo import LocalBoardSyncManifestRepository
        self.manifest_repository = LocalBoardSyncManifestRepository(self.test_manifest_path)

        # 2. 동기화 서비스 초기화
        self.sync_service = BoardFileSyncService(
            repository=self.repository,
            drive_adapter=self.drive_adapter,
            theme_folder_id=self.theme_folder_id,
            manifest_repository=self.manifest_repository
        )

        # 기존 드라이브 잔재 청소를 위한 사전 안전 제거 집행
        asyncio.run(self._cleanup_drive())

        yield  # 🌟 테스트 실행부 진행

        # 3. Teardown: 테스트 완료 후 흔적 완전 청소
        # 로컬 임시 파일 삭제
        for f in self.test_board_dir.glob("*"):
            try:
                f.unlink()
            except Exception:
                pass
        try:
            self.test_board_dir.rmdir()
        except Exception:
            pass

        # 구글 드라이브 임시 파일 삭제 (1단계에서 추가한 delete_file 활용!)
        asyncio.run(self._cleanup_drive())

    async def _cleanup_drive(self):
        """구글 드라이브 내 임시 테스트 파일들을 영구 삭제합니다."""
        await self.drive_adapter.delete_file(f"{self.test_virtual_id}.json", root_id=self.theme_folder_id)
        await self.drive_adapter.delete_file(f"{self.test_theme_id}.json", root_id=self.theme_folder_id)
        await self.drive_adapter.delete_file(self.manifest_name, root_id=self.theme_folder_id)

    async def test_integration_sync_flow_full_lifecycle(self):
        """실제 구글 드라이브와 양방향 CRUD 동기화 라이프사이클을 통째로 검증합니다."""
        # --- PHASE 1: 최초 업로드 시나리오 (로컬에만 새 보드가 생성된 상황) ---
        # 1. 로컬에 가상 보드 및 테마 보드 저장
        self.repository.save(self.test_board_virtual)
        self.repository.save(self.test_board_theme)

        # 2. 로컬 매니페스트에 등록
        self.sync_service.update_local_manifest(self.test_virtual_id)
        self.sync_service.update_local_manifest(self.test_theme_id)

        # 3. 드라이브와 동기화 실행 (Upload 유발)
        success = await self.sync_service.sync_with_drive()
        assert success is True, "최초 업로드 동기화가 실패했습니다."

        # 4. 검증: 구글 드라이브 상에 파일들이 실제로 존재해야 함
        virtual_exists = await self.drive_adapter.path_exists(
            f"{self.test_virtual_id}.json", root_id=self.theme_folder_id
        )
        theme_exists = await self.drive_adapter.path_exists(
            f"{self.test_theme_id}.json", root_id=self.theme_folder_id
        )
        manifest_exists = await self.drive_adapter.path_exists(self.manifest_name, root_id=self.theme_folder_id)

        assert virtual_exists is True, "가상 보드 파일이 구글 드라이브에 올라가지 않았습니다."
        assert theme_exists is True, "테마 보드 파일이 구글 드라이브에 올라가지 않았습니다."
        assert manifest_exists is True, "상태 매니페스트가 구글 드라이브에 올라가지 않았습니다."

        # --- PHASE 2: 최초 다운로드 시나리오 (로컬엔 파일이 없는데 원격에만 있는 상황) ---
        # 1. 로컬 디렉토리 내의 보드 파일들을 물리적으로 지움
        (self.test_board_dir / f"{self.test_virtual_id}.json").unlink()
        (self.test_board_dir / f"{self.test_theme_id}.json").unlink()
        self.test_manifest_path.unlink()  # 로컬 매니페스트도 삭제

        # 2. 동기화 실행 (Download 유발)
        success = await self.sync_service.sync_with_drive()
        assert success is True, "다운로드 동기화가 실패했습니다."

        # 3. 검증: 구글 드라이브에서 보드를 다운로드하여 로컬에 복구했어야 함
        assert (self.test_board_dir / f"{self.test_virtual_id}.json").exists() is True, (
            "가상 보드가 원격으로부터 다운로드되지 않았습니다."
        )
        assert (self.test_board_dir / f"{self.test_theme_id}.json").exists() is True, (
            "테마 보드가 원격으로부터 다운로드되지 않았습니다."
        )

        # --- PHASE 3: 원격 물리적 삭제 동기화 시나리오 (deleted=True 상태를 로컬 물리 삭제로 유도) ---
        # 1. 로컬 매니페스트에서 테마 보드를 deleted=True로 마킹
        self.sync_service.update_local_manifest(self.test_theme_id, deleted=True)

        # 2. 동기화 실행 (Delete & Upload 유발)
        success = await self.sync_service.sync_with_drive()
        assert success is True, "삭제 동기화가 실패했습니다."

        # 3. 검증: 로컬 저장소에서 테마 보드가 안전하게 삭제되었어야 함
        assert (self.test_board_dir / f"{self.test_theme_id}.json").exists() is False, (
            "테마 보드가 로컬 디스크에서 삭제되지 않았습니다."
        )

