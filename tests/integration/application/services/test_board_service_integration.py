"""BoardService 통합 테스트 - 실제 어댑터와의 연동 검증."""

import shutil
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from synapstock.application.services.command_service import BoardCommandService
from synapstock.application.services.query_service import BoardQueryService
from synapstock.application.services.sync_service import BoardSyncService
from synapstock.domain.models import Board, Stock
from synapstock.domain.ports import MindmapPort, TickerSearchPort
from synapstock.infrastructure.adapters.local.board_repo import LocalBoardRepository

FIXTURES_DIR = Path(__file__).parents[3] / "fixtures" / "folder_mindmap"


@pytest.fixture
def query_service(tmp_path):
    repo = LocalBoardRepository(root_dir=tmp_path)
    ticker_search = MagicMock(spec=TickerSearchPort)
    return BoardQueryService(repository=repo, ticker_search=ticker_search)

@pytest.fixture
def command_service(tmp_path):
    repo = LocalBoardRepository(root_dir=tmp_path)
    return BoardCommandService(repository=repo)

@pytest.fixture
def sync_service():
    mindmap = MagicMock(spec=MindmapPort)
    ticker_search = MagicMock(spec=TickerSearchPort)
    return BoardSyncService(mindmap=mindmap, ticker_search=ticker_search)


@pytest.fixture
def fixture_query_service():
    """IT 픽스처 폴더 기반 읽기 전용 서비스 픽스처."""
    repo = LocalBoardRepository(root_dir=FIXTURES_DIR)
    ticker_search = MagicMock(spec=TickerSearchPort)
    return BoardQueryService(repository=repo, ticker_search=ticker_search)


@pytest.fixture
def mutable_services(tmp_path):
    """픽스처를 tmp_path에 복사한 뒤 서비스를 반환한다 (변이 테스트용)."""
    dest = tmp_path / "board"
    shutil.copytree(FIXTURES_DIR, dest)
    repo = LocalBoardRepository(root_dir=dest)
    ticker_search = MagicMock(spec=TickerSearchPort)
    query = BoardQueryService(repository=repo, ticker_search=ticker_search)
    command = BoardCommandService(repository=repo)
    return query, command


class TestBoardServiceIntegration:
    """BoardService + LocalFolderMindmapAdapter 통합 테스트."""

    def test_save_and_load_roundtrip(self, query_service, command_service):
        """save 후 load하면 동일한 Board 구조가 복원되어야 한다."""
        board = Board(name="테스트보드")
        sector = board.root.add_child("섹터A")
        sector.stocks.append(Stock(name="삼성전자", ticker="005930"))

        # command_service를 통해 간접적으로 repo에 저장 (실제로는 repo.save() 호출)
        command_service._repository.save(board)
        loaded = query_service.load_board("테스트보드")

        assert loaded.name == "테스트보드"
        assert loaded.root.nodes[0].name == "섹터A"
        assert loaded.root.nodes[0].stocks[0].ticker == "005930"

    def test_list_boards_after_save(self, query_service, command_service):
        """save한 Board 이름이 list_boards()에 포함되어야 한다."""
        command_service._repository.save(Board(id="theme_A보드", name="A보드"))
        command_service._repository.save(Board(id="theme_B보드", name="B보드"))

        boards = query_service.list_boards()

        assert "theme_A보드" in boards
        assert "theme_B보드" in boards

    def test_load_not_found_raises(self, query_service):
        """존재하지 않는 Board를 load하면 FileNotFoundError가 발생해야 한다."""
        with pytest.raises(FileNotFoundError):
            query_service.load_board("없는보드")

    def test_load_it_fixture(self, fixture_query_service):
        """IT 픽스처 보드를 서비스를 통해 로드하면 올바른 트리가 반환되어야 한다."""
        board = fixture_query_service.load_board("IT")

        assert board.name == "IT"
        assert board.root.depth == 0
        names = {n.name for n in board.root.nodes}
        assert names == {"인터넷", "보안", "소프트웨어"}

    def test_load_it_deep_structure(self, fixture_query_service):
        """IT 픽스처의 depth 3 노드(네트워크)를 서비스를 통해 올바르게 복원해야 한다."""
        board = fixture_query_service.load_board("IT")
        security = next(n for n in board.root.nodes if n.name == "보안")
        jeongbo = next(n for n in security.nodes if n.name == "정보보안")
        network = next(n for n in jeongbo.nodes if n.name == "네트워크")

        assert network.depth == 3
        tickers = {s.ticker for s in network.stocks}
        assert tickers == {"053800", "136240", "263860"}

    def test_add_stock_and_reload(self, mutable_services):
        """서비스를 통해 종목 추가 후 저장하면 다시 로드할 때 반영되어야 한다."""
        query, command = mutable_services
        board = query.load_board("IT")

        # 직접 도메인 모델 조작 후 command_service로 저장
        internet = next(n for n in board.root.nodes if n.name == "인터넷")
        internet.stocks.append(Stock(name="카카오뱅크", ticker="323410"))
        command._repository.save(board)

        reloaded = query.load_board("IT")
        internet_r = next(n for n in reloaded.root.nodes if n.name == "인터넷")
        tickers = {s.ticker for s in internet_r.stocks}
        assert "323410" in tickers
        assert len(tickers) == 4

    def test_save_overwrites_removes_old_data(self, mutable_services):
        """save로 보드를 덮어쓸 때 이전 데이터(삭제된 종목)가 남아있으면 안 된다."""
        query, command = mutable_services
        board = query.load_board("IT")
        internet = next(n for n in board.root.nodes if n.name == "인터넷")
        internet.stocks = [s for s in internet.stocks if s.ticker != "035420"]
        command._repository.save(board)

        reloaded = query.load_board("IT")
        internet_r = next(n for n in reloaded.root.nodes if n.name == "인터넷")
        tickers = {s.ticker for s in internet_r.stocks}
        assert "035420" not in tickers
        assert len(tickers) == 2

    def test_boards_are_isolated(self, query_service, command_service):
        """서로 다른 보드는 독립적으로 저장/로드되어야 한다."""
        board_a = Board(name="보드A")
        board_a.root.add_child("섹터X").stocks.append(Stock(name="삼성전자", ticker="005930"))

        board_b = Board(name="보드B")
        board_b.root.add_child("섹터Y").stocks.append(Stock(name="LG전자", ticker="066570"))

        command_service._repository.save(board_a)
        command_service._repository.save(board_b)

        loaded_a = query_service.load_board("보드A")
        loaded_b = query_service.load_board("보드B")

        tickers_a = {s.ticker for n in loaded_a.root.nodes for s in n.stocks}
        tickers_b = {s.ticker for n in loaded_b.root.nodes for s in n.stocks}
        assert tickers_a == {"005930"}
        assert tickers_b == {"066570"}
        assert tickers_a.isdisjoint(tickers_b)

