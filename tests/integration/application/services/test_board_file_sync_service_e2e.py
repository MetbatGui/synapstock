import asyncio
import os
import uuid
import json
import pytest
import pytest_asyncio
from datetime import UTC, datetime

from evenezer.application.services.board_file_sync_service import BoardFileSyncService
from evenezer.domain.models import Board, Node, Stock
from evenezer.infrastructure.adapters.google.google_drive_adapter import GoogleDriveAdapter
from evenezer.infrastructure.adapters.local.board_repo import LocalBoardRepository
from evenezer.infrastructure.config import AppConfig

TOKEN_PATH = "secrets/token.json"
token_exists = os.path.exists(TOKEN_PATH)


@pytest.mark.asyncio
@pytest.mark.skipif(not token_exists, reason="secrets/token.json 파일이 없어 구글 드라이브 e2e 테스트를 스킵합니다.")
class TestBoardFileSyncServiceE2E:
    """구글 드라이브 내 임시 격리 폴더를 생성하여 최악의 데이터 유실 시나리오를 검증하는 E2E 테스트."""

    @pytest_asyncio.fixture(autouse=True)
    async def setup_e2e_sandbox(self):
        # 1. 설정 로드 및 드라이브 어댑터 조립
        self.config = AppConfig.load()
        self.drive_adapter = GoogleDriveAdapter(
            token_file=str(self.config.secrets_dir / "token.json"),
            client_secret_file=str(self.config.secrets_dir / "client_secret.json")
        )
        self.theme_folder_id = self.config.theme_folder_id
        if not self.theme_folder_id:
            pytest.skip("GOOGLE_DRIVE_THEME_FOLDER_ID 환경 변수가 설정되지 않아 E2E 테스트를 스킵합니다.")

        # 2. 구글 드라이브 내 임시 격리 폴더 생성
        self.temp_folder_name = f"theme_e2e_test_dir_{uuid.uuid4().hex[:8]}"
        await self.drive_adapter.ensure_directory(self.temp_folder_name, root_id=self.theme_folder_id)
        
        # 생성된 임시 폴더의 구글 드라이브 ID 획득
        self.temp_folder_id = self.drive_adapter._get_file_id(self.temp_folder_name, root_id=self.theme_folder_id)
        assert self.temp_folder_id is not None, "구글 드라이브 임시 테스트 폴더 생성에 실패했습니다."

        # 3. 로컬 임시 디렉토리 생성
        self.test_board_dir = self.config.data_dir / f"test_board_e2e_{uuid.uuid4().hex[:8]}"
        self.test_board_dir.mkdir(parents=True, exist_ok=True)
        self.repository = LocalBoardRepository(self.test_board_dir)

        # 4. 임시 매니페스트 레포지토리 초기화
        from evenezer.infrastructure.adapters.local.board_repo import LocalBoardSyncManifestRepository
        self.manifest_path = self.test_board_dir / "board_sync_manifest.json"
        self.manifest_repository = LocalBoardSyncManifestRepository(self.manifest_path)

        # 5. 동기화 서비스 초기화 (임시 폴더 ID 주입)
        self.sync_service = BoardFileSyncService(
            repository=self.repository,
            drive_adapter=self.drive_adapter,
            theme_folder_id=self.temp_folder_id,
            manifest_repository=self.manifest_repository
        )

        yield  # 🌟 테스트 실행

        # 6. Teardown: 로컬 및 구글 드라이브 테스트 흔적 완전 소거
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

        # 구글 드라이브 임시 폴더 통째로 영구 삭제 (하위 파일 자동 소거)
        await self.drive_adapter.delete_file(self.temp_folder_name, root_id=self.theme_folder_id)

    async def test_e2e_data_loss_prevention_on_unmanifested_existing_board(self):
        """최악의 데이터 유실 시나리오 E2E 검증.
        
        시나리오:
          - 구글 드라이브에는 꽉 찬 데이터 보드('theme_e2e_test_board.json')가 이미 존재한다.
          - 로컬 및 구글 드라이브 매니페스트에는 이 보드 정보가 누락되어 있다.
          - 로컬 디렉터리에는 예전에 생성된 동명의 '빈 보드' 파일이 존재한다.
        
        기대 결과:
          - 동기화 실행 시, 로컬의 빈 보드가 구글 드라이브를 덮어쓰지 않고,
          - 구글 드라이브에 있던 제대로 된 원격 보드 데이터를 다운로드받아 로컬 빈 파일을 채우고 안전하게 보존해야 한다.
        """
        board_id = "theme_e2e_test_board"
        board_filename = f"{board_id}.json"

        # 1. 구글 드라이브 임시 폴더에 꽉 찬 제대로 된 보드 파일 사전 업로드
        full_board = Board(id=board_id, name="e2e_test_board")
        full_board.nodes = {
            "e2e_test_board": Node(name="e2e_test_board", depth=0, parent_path=None),
            "e2e_test_board/반도체": Node(
                name="반도체",
                depth=1,
                parent_path="e2e_test_board",
                stocks=[
                    Stock(name="삼성전자", ticker="005930"),
                    Stock(name="SGA", ticker="049470")  # 표준 6자리 티커
                ]
            )
        }
        
        full_board_bytes = full_board.model_dump_json(indent=2, exclude={"id"}, exclude_defaults=True).encode("utf-8")
        upload_ok = await self.drive_adapter.put_file(board_filename, full_board_bytes, root_id=self.temp_folder_id)
        assert upload_ok is True, "임시 보드 파일 구글 드라이브 업로드 실패"

        # 2. 로컬 디렉터리에는 루트 노드만 있는 '빈 보드' 파일 생성 (유실 유발 환경 조성)
        empty_board = Board(id=board_id, name="e2e_test_board")
        self.repository.save(empty_board)

        # 3. 로컬 매니페스트는 비어 있는 상태로 유지 (원격 매니페스트도 없는 상태)
        assert not self.manifest_path.exists() or len(self.manifest_repository.load().boards) == 0

        # 4. 동기화 실행 (양방향 동기화 구동)
        sync_success = await self.sync_service.sync_with_drive()
        assert sync_success is True, "양방향 동기화 API가 실패했습니다."

        # 5. 검증: 로컬 보드 파일이 구글 드라이브에 있던 꽉 찬 보드로 덮어써져 복구되었는지 확인
        loaded_local_board = self.repository.load(board_id)
        assert "e2e_test_board/반도체" in loaded_local_board.nodes, "구글 드라이브의 원격 보드가 로컬로 다운로드되지 않았습니다."
        
        stocks = loaded_local_board.nodes["e2e_test_board/반도체"].stocks
        assert len(stocks) == 2, "보드 내 주식 종목 개수가 맞지 않습니다."
        assert any(s.name == "삼성전자" and s.ticker == "005930" for s in stocks)
        assert any(s.name == "SGA" and s.ticker == "049470" for s in stocks)

        # 6. 검증: 구글 드라이브 임시 폴더 내의 보드 파일도 덮어쓰기 유실 없이 원본 내용이 그대로 보존되었는지 검증
        remote_data = await self.drive_adapter.get_file(board_filename, root_id=self.temp_folder_id)
        assert remote_data is not None, "구글 드라이브에 파일이 존재하지 않습니다."
        
        remote_json = json.loads(remote_data.decode("utf-8"))
        assert "nodes" in remote_json, "구글 드라이브 보드 내용이 손상되었습니다 (nodes 없음)."
        assert "e2e_test_board/반도체" in remote_json["nodes"], "구글 드라이브 보드의 세부 노드가 날아가 비워졌습니다."
