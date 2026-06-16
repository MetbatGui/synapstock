from unittest.mock import MagicMock, AsyncMock

import pytest

from evenezer.application.services.command_service import BoardCommandService
from evenezer.domain.models import Board, Stock


class TestBoardCommandServiceSyncHook:
    """BoardCommandService 명령 호출 시 동기화 서비스 훅이 올바르게 격발되는지 검증하는 단위 테스트."""

    @pytest.fixture
    def setup_mocks(self):
        """Mock 리포지토리와 Mock 동기화 서비스를 생성하여 주입받습니다."""
        self.mock_repo = MagicMock()
        self.mock_sync = MagicMock()
        self.mock_sync.handle_stock_addition_trigger = AsyncMock()
        self.mock_sync.handle_stock_deletion_trigger = AsyncMock()
        self.mock_sync.sync_with_drive = AsyncMock()
        self.service = BoardCommandService(repository=self.mock_repo, sync_service=self.mock_sync)

        # 기본 테스트 보드 모형
        self.test_board = Board(
            id="theme_test",
            name="test"
        )
        self.mock_repo.load.return_value = self.test_board

    @pytest.mark.usefixtures("setup_mocks")
    def test_add_node_sync_hook(self):
        """노드 추가 성공 시 동기화 매니페스트 갱신 훅이 격발되는지 검증."""
        success = self.service.add_node("theme_test", "test", "child_node")

        assert success is True
        self.mock_repo.save.assert_called_once_with(self.test_board)
        # 매니페스트 갱신 훅 검증
        self.mock_sync.update_local_manifest.assert_called_once_with("theme_test", deleted=False)

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("setup_mocks")
    async def test_add_stock_sync_hook(self):
        """종목 추가 성공 시 동기화 매니페스트 갱신 훅이 격발되는지 검증."""
        success = await self.service.add_stock("theme_test", "test", "삼성전자", "005930")

        assert success is True
        self.mock_repo.save.assert_called_once_with(self.test_board)
        # 매니페스트 갱신 훅 검증
        self.mock_sync.update_local_manifest.assert_called_once_with("theme_test", deleted=False)

    @pytest.mark.usefixtures("setup_mocks")
    def test_delete_node_sync_hook(self):
        """노드 삭제 성공 시 동기화 매니페스트 갱신 훅이 격발되는지 검증."""
        # 삭제 대상 자식 노드 추가
        self.test_board.add_node("test", "delete_me")
        self.test_board.pull_events()  # 임시 노드 추가 시 누적된 도메인 이벤트 클리어 (중복 호출 방지)

        success = self.service.delete_node("theme_test", "delete_me")

        assert success is True
        self.mock_repo.save.assert_called_once_with(self.test_board)
        # 매니페스트 갱신 훅 검증
        self.mock_sync.update_local_manifest.assert_called_once_with("theme_test", deleted=False)

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("setup_mocks")
    async def test_delete_stock_sync_hook(self):
        """종목 삭제 성공 시 동기화 매니페스트 갱신 훅이 격발되는지 검증."""
        # 삭제 대상 종목 추가
        self.test_board.add_stock_to_node("test", Stock(name="삼성전자", ticker="005930"))
        self.test_board.pull_events()  # 임시 종목 추가 시 누적된 도메인 이벤트 클리어 (중복 호출 방지)

        success = await self.service.delete_stock("theme_test", "005930")

        assert success is True
        self.mock_repo.save.assert_called_once_with(self.test_board)
        # 매니페스트 갱신 훅 검증
        self.mock_sync.update_local_manifest.assert_called_once_with("theme_test", deleted=False)

    @pytest.mark.usefixtures("setup_mocks")
    def test_create_board_sync_hook(self):
        """신규 보드 생성 시 매니페스트 편입 훅이 격발되는지 검증."""
        success = self.service.create_board("virtual_new_board")

        assert success is True
        self.mock_repo.save.assert_called_once()
        # 매니페스트 편입 훅 검증
        self.mock_sync.update_local_manifest.assert_called_once_with("virtual_new_board", deleted=False)

    @pytest.mark.usefixtures("setup_mocks")
    def test_delete_board_sync_hook(self):
        """보드 삭제 성공 시 매니페스트에 deleted=True 마킹이 남는지 검증."""
        success = self.service.delete_board("virtual_delete_board")

        assert success is True
        self.mock_repo.delete.assert_called_once_with("virtual_delete_board")
        # 삭제 상태 마킹 훅 검증
        self.mock_sync.update_local_manifest.assert_called_once_with("virtual_delete_board", deleted=True)

    def test_sync_service_none_fallback(self):
        """동기화 서비스가 None으로 주입되어도 기본 CRUD 기능이 에러 없이 무사히 완수되는지 검증 (하위 호환성)."""
        mock_repo = MagicMock()
        service = BoardCommandService(repository=mock_repo, sync_service=None)

        test_board = Board(
            id="theme_test",
            name="test"
        )
        mock_repo.load.return_value = test_board

        success = service.add_node("theme_test", "test", "fallback_node")
        assert success is True
        mock_repo.save.assert_called_once_with(test_board)
