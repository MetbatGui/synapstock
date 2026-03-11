"""BoardService 통합 테스트 - 실제 어댑터와의 연동 검증."""

import shutil
from pathlib import Path

import pytest

from synapstock.adapters.local.folder_mindmap import LocalFolderMindmapAdapter
from synapstock.domain.models import Board, Stock
from synapstock.services.board_service import BoardService

FIXTURES_DIR = Path(__file__).parents[2] / "fixtures" / "folder_mindmap"


@pytest.fixture
def service(tmp_path):
    """실제 LocalFolderMindmapAdapter를 사용하는 BoardService 픽스처."""
    adapter = LocalFolderMindmapAdapter(root_dir=tmp_path)
    return BoardService(mindmap=adapter)


@pytest.fixture
def fixture_service():
    """IT 픽스처 폴더 기반 읽기 전용 서비스 픽스처."""
    adapter = LocalFolderMindmapAdapter(root_dir=FIXTURES_DIR)
    return BoardService(mindmap=adapter)


@pytest.fixture
def mutable_service(tmp_path):
    """픽스처를 tmp_path에 복사한 뒤 서비스를 반환한다 (변이 테스트용)."""
    dest = tmp_path / "folder_mindmap"
    shutil.copytree(FIXTURES_DIR, dest)
    adapter = LocalFolderMindmapAdapter(root_dir=dest)
    return BoardService(mindmap=adapter)


class TestBoardServiceIntegration:
    """BoardService + LocalFolderMindmapAdapter 통합 테스트."""

    def test_save_and_load_roundtrip(self, service):
        """save 후 load하면 동일한 Board 구조가 복원되어야 한다.

        Arrange: 노드와 종목이 있는 Board를 생성
        Act: service.save() 후 service.load() 호출
        Assert: 복원된 Board의 구조가 원본과 일치하는지 확인
        """
        board = Board(name="테스트보드")
        sector = board.root.add_child("섹터A")
        sector.stocks.append(Stock(name="삼성전자", ticker="005930"))

        service.save(board)
        loaded = service.load("테스트보드")

        assert loaded.name == "테스트보드"
        assert loaded.root.nodes[0].name == "섹터A"
        assert loaded.root.nodes[0].stocks[0].ticker == "005930"

    def test_list_boards_after_save(self, service):
        """save한 Board 이름이 list_boards()에 포함되어야 한다.

        Arrange: Board 2개 생성
        Act: 각각 save 후 list_boards() 호출
        Assert: 저장된 Board 이름이 목록에 포함되는지 확인
        """
        service.save(Board(name="A보드"))
        service.save(Board(name="B보드"))

        boards = service.list_boards()

        assert "A보드" in boards
        assert "B보드" in boards

    def test_load_not_found_raises(self, service):
        """존재하지 않는 Board를 load하면 FileNotFoundError가 발생해야 한다.

        Arrange: 저장된 Board 없음
        Act: service.load("없는보드") 호출
        Assert: FileNotFoundError 발생 확인
        """
        with pytest.raises(FileNotFoundError):
            service.load("없는보드")

    def test_load_it_fixture(self, fixture_service):
        """IT 픽스처 보드를 서비스를 통해 로드하면 올바른 트리가 반환되어야 한다.

        Arrange: 실제 fixture/folder_mindmap/IT 폴더 기반 서비스 준비
        Act: service.load("IT") 호출
        Assert: Board 이름, 루트 노드, 1depth 노드 구성 확인
        """
        board = fixture_service.load("IT")

        assert board.name == "IT"
        assert board.root.depth == 0
        names = {n.name for n in board.root.nodes}
        assert names == {"인터넷", "보안", "소프트웨어"}

    def test_load_it_deep_structure(self, fixture_service):
        """IT 픽스처의 depth 3 노드(네트워크)를 서비스를 통해 올바르게 복원해야 한다.

        Arrange: 실제 fixture/folder_mindmap/IT 폴더 기반 서비스 준비
        Act: service.load("IT") 호출 후 depth 3 노드 탐색
        Assert: 네트워크 노드의 depth 및 종목 구성 확인
        """
        board = fixture_service.load("IT")
        security = next(n for n in board.root.nodes if n.name == "보안")
        jeongbo = next(n for n in security.nodes if n.name == "정보보안")
        network = next(n for n in jeongbo.nodes if n.name == "네트워크")

        assert network.depth == 3
        tickers = {s.ticker for s in network.stocks}
        assert tickers == {"053800", "136240", "263860"}

    def test_add_stock_and_reload(self, mutable_service):
        """서비스를 통해 종목 추가 후 저장하면 다시 로드할 때 반영되어야 한다.

        Arrange: IT 픽스처 복사본에서 Board 로드
        Act: 인터넷 노드에 카카오뱅크 추가 후 save, load
        Assert: 재로드 시 카카오뱅크 종목이 포함되어 있는지 확인
        """
        board = mutable_service.load("IT")
        internet = next(n for n in board.root.nodes if n.name == "인터넷")
        internet.stocks.append(Stock(name="카카오뱅크", ticker="323410"))
        mutable_service.save(board)

        reloaded = mutable_service.load("IT")
        internet_r = next(n for n in reloaded.root.nodes if n.name == "인터넷")
        tickers = {s.ticker for s in internet_r.stocks}
        assert "323410" in tickers
        assert len(tickers) == 4

    def test_save_overwrites_removes_old_data(self, mutable_service):
        """save로 보드를 덮어쓸 때 이전 데이터(삭제된 종목)가 남아있으면 안 된다.

        Arrange: IT 픽스처 로드 후 인터넷 노드에서 NAVER 제거
        Act: save 후 reload
        Assert: NAVER가 더이상 존재하지 않는지 확인 (오염 데이터 잔존 방지)
        """
        board = mutable_service.load("IT")
        internet = next(n for n in board.root.nodes if n.name == "인터넷")
        internet.stocks = [s for s in internet.stocks if s.ticker != "035420"]
        mutable_service.save(board)

        reloaded = mutable_service.load("IT")
        internet_r = next(n for n in reloaded.root.nodes if n.name == "인터넷")
        tickers = {s.ticker for s in internet_r.stocks}
        assert "035420" not in tickers
        assert len(tickers) == 2

    def test_boards_are_isolated(self, service):
        """서로 다른 보드는 독립적으로 저장/로드되어야 한다.

        Arrange: 구조가 다른 보드 A, B를 각각 생성
        Act: 두 보드를 save 후 각각 load
        Assert: 보드 A 로드 시 보드 B의 데이터가 혼입되지 않는지 확인
        """
        board_a = Board(name="보드A")
        board_a.root.add_child("섹터X").stocks.append(Stock(name="삼성전자", ticker="005930"))

        board_b = Board(name="보드B")
        board_b.root.add_child("섹터Y").stocks.append(Stock(name="LG전자", ticker="066570"))

        service.save(board_a)
        service.save(board_b)

        loaded_a = service.load("보드A")
        loaded_b = service.load("보드B")

        tickers_a = {s.ticker for n in loaded_a.root.nodes for s in n.stocks}
        tickers_b = {s.ticker for n in loaded_b.root.nodes for s in n.stocks}
        assert tickers_a == {"005930"}
        assert tickers_b == {"066570"}
        assert tickers_a.isdisjoint(tickers_b)

