"""LocalFolderMindmapAdapter 단위 테스트."""

import shutil
from pathlib import Path

import pytest

from synapstock.adapters.local.folder_mindmap import LocalFolderMindmapAdapter
from synapstock.domain.models import Board, Stock

FIXTURES_DIR = Path(__file__).parents[3] / "fixtures" / "folder_mindmap"


@pytest.fixture
def adapter(tmp_path):
    """임시 디렉터리 기반 어댑터 픽스처 (읽기/쓰기 테스트용)."""
    return LocalFolderMindmapAdapter(root_dir=tmp_path)


@pytest.fixture
def fixture_adapter():
    """tests/fixtures/folder_mindmap/ 기반 읽기 전용 어댑터 픽스처."""
    return LocalFolderMindmapAdapter(root_dir=FIXTURES_DIR)


@pytest.fixture
def mutable_adapter(tmp_path):
    """픽스처 폴더를 tmp_path에 복사한 뒤 어댑터를 반환한다.

    테스트 종료 시 tmp_path가 자동으로 teardown되므로 원본 픽스처가 보호된다.
    """
    dest = tmp_path / "folder_mindmap"
    shutil.copytree(FIXTURES_DIR, dest)
    return LocalFolderMindmapAdapter(root_dir=dest)


@pytest.fixture
def simple_board() -> Board:
    """단순 보드 픽스처 (1depth 노드 + 종목)."""
    board = Board(name="테스트보드")
    sector = board.root.add_child("섹터A")
    sector.stocks.append(Stock(name="삼성전자", ticker="005930"))
    return board


class TestLocalFolderMindmapAdapter:
    """LocalFolderMindmapAdapter 기본 동작 테스트."""

    def test_save_creates_folder_structure(self, adapter, simple_board, tmp_path):
        """save() 호출 시 보드/루트노드/섹터 폴더와 종목 파일이 생성되어야 한다."""
        adapter.save(simple_board)

        board_dir = tmp_path / "테스트보드"
        root_dir = board_dir / "테스트보드"
        sector_dir = root_dir / "섹터A"
        stock_file = sector_dir / "삼성전자.json"

        assert board_dir.is_dir()
        assert root_dir.is_dir()
        assert sector_dir.is_dir()
        assert stock_file.exists()

    def test_save_and_load_roundtrip(self, adapter, simple_board):
        """save 후 load하면 동일한 Board 구조여야 한다."""
        adapter.save(simple_board)
        loaded = adapter.load("테스트보드")

        assert loaded.name == simple_board.name
        assert loaded.root.name == simple_board.root.name
        assert loaded.root.depth == 0
        assert len(loaded.root.nodes) == 1
        assert loaded.root.nodes[0].name == "섹터A"
        assert loaded.root.nodes[0].depth == 1
        assert loaded.root.nodes[0].stocks[0].ticker == "005930"

    def test_load_not_found(self, adapter):
        """존재하지 않는 Board 로드 시 FileNotFoundError가 발생해야 한다."""
        with pytest.raises(FileNotFoundError, match="없는보드"):
            adapter.load("없는보드")

    def test_list_boards_empty(self, adapter):
        """저장된 Board가 없으면 빈 리스트를 반환해야 한다."""
        assert adapter.list_boards() == []

    def test_list_boards(self, adapter):
        """저장된 Board 이름 목록을 정렬하여 반환해야 한다."""
        adapter.save(Board(name="B보드"))
        adapter.save(Board(name="A보드"))
        adapter.save(Board(name="C보드"))
        assert adapter.list_boards() == ["A보드", "B보드", "C보드"]

    def test_save_overwrites_existing(self, adapter):
        """같은 이름으로 다시 save()하면 덮어써야 한다."""
        board = Board(name="보드")
        adapter.save(board)

        board.root.add_child("새섹터")
        adapter.save(board)

        loaded = adapter.load("보드")
        assert len(loaded.root.nodes) == 1
        assert loaded.root.nodes[0].name == "새섹터"

    def test_load_deep_tree(self, adapter):
        """다층 트리 구조도 정확하게 복원되어야 한다."""
        board = Board(name="딥트리")
        child = board.root.add_child("D1")
        grandchild = child.add_child("D2")
        grandchild.stocks.append(Stock(name="테스트주", ticker="999999"))
        adapter.save(board)

        loaded = adapter.load("딥트리")
        assert loaded.root.nodes[0].depth == 1
        assert loaded.root.nodes[0].nodes[0].depth == 2
        assert loaded.root.nodes[0].nodes[0].stocks[0].ticker == "999999"

    def test_stock_json_content(self, adapter, tmp_path):
        """저장된 종목 .json 파일이 올바른 내용을 가져야 한다."""
        board = Board(name="주식보드")
        board.root.stocks.append(Stock(name="현대차", ticker="005380"))
        adapter.save(board)

        stock_file = tmp_path / "주식보드" / "주식보드" / "현대차.json"
        import json
        data = json.loads(stock_file.read_text(encoding="utf-8"))
        assert data["name"] == "현대차"
        assert data["ticker"] == "005380"


class TestFixtureFolderMindmap:
    """tests/fixtures/folder_mindmap/ 기반 실제 파일 로드 테스트 (IT.json 동일 구조)."""

    def test_load_it_board(self, fixture_adapter):
        """IT 폴더를 로드하면 Board name이 'IT'이어야 한다."""
        board = fixture_adapter.load("IT")
        assert board.name == "IT"
        assert board.root.name == "IT"
        assert board.root.depth == 0

    def test_it_board_top_level_nodes(self, fixture_adapter):
        """IT 보드의 1depth 노드는 인터넷·보안·소프트웨어 3개여야 한다."""
        board = fixture_adapter.load("IT")
        names = {n.name for n in board.root.nodes}
        assert names == {"인터넷", "보안", "소프트웨어"}

    def test_internet_has_3_stocks(self, fixture_adapter):
        """인터넷 노드에 종목이 3개(NAVER·카카오·이스트에이드) 있어야 한다."""
        board = fixture_adapter.load("IT")
        internet = next(n for n in board.root.nodes if n.name == "인터넷")
        tickers = {s.ticker for s in internet.stocks}
        assert tickers == {"035420", "035720", "389240"}

    def test_internet_depth_is_1(self, fixture_adapter):
        """인터넷 노드의 depth는 1이어야 한다."""
        board = fixture_adapter.load("IT")
        internet = next(n for n in board.root.nodes if n.name == "인터넷")
        assert internet.depth == 1

    def test_security_has_2_subnodes(self, fixture_adapter):
        """보안 노드는 정보보안·보안 서비스 2개 서브노드를 가져야 한다."""
        board = fixture_adapter.load("IT")
        security = next(n for n in board.root.nodes if n.name == "보안")
        names = {n.name for n in security.nodes}
        assert names == {"정보보안", "보안 서비스"}

    def test_jeongbo_security_has_4_subnodes(self, fixture_adapter):
        """정보보안 노드는 암호인증·네트워크·보안관리·정보 유출 방지 4개를 가져야 한다."""
        board = fixture_adapter.load("IT")
        security = next(n for n in board.root.nodes if n.name == "보안")
        jeongbo = next(n for n in security.nodes if n.name == "정보보안")
        names = {n.name for n in jeongbo.nodes}
        assert names == {"암호인증", "네트워크", "보안관리", "정보 유출 방지"}

    def test_network_node_depth_is_3(self, fixture_adapter):
        """네트워크 노드의 depth는 3이어야 한다."""
        board = fixture_adapter.load("IT")
        security = next(n for n in board.root.nodes if n.name == "보안")
        jeongbo = next(n for n in security.nodes if n.name == "정보보안")
        network = next(n for n in jeongbo.nodes if n.name == "네트워크")
        assert network.depth == 3

    def test_network_node_stocks(self, fixture_adapter):
        """네트워크 노드에 안랩·윈스·지니언스가 포함되어야 한다."""
        board = fixture_adapter.load("IT")
        security = next(n for n in board.root.nodes if n.name == "보안")
        jeongbo = next(n for n in security.nodes if n.name == "정보보안")
        network = next(n for n in jeongbo.nodes if n.name == "네트워크")
        tickers = {s.ticker for s in network.stocks}
        assert tickers == {"053800", "136240", "263860"}

    def test_security_service_subnodes(self, fixture_adapter):
        """보안 서비스 노드는 관제·장비·인증서 3개를 가져야 한다."""
        board = fixture_adapter.load("IT")
        security = next(n for n in board.root.nodes if n.name == "보안")
        service = next(n for n in security.nodes if n.name == "보안 서비스")
        names = {n.name for n in service.nodes}
        assert names == {"관제", "장비", "인증서"}

    def test_software_has_3_subnodes(self, fixture_adapter):
        """소프트웨어 노드는 금융·업무·자동화 3개 서브노드를 가져야 한다."""
        board = fixture_adapter.load("IT")
        sw = next(n for n in board.root.nodes if n.name == "소프트웨어")
        names = {n.name for n in sw.nodes}
        assert names == {"금융", "업무", "자동화"}

    def test_software_finance_stocks(self, fixture_adapter):
        """소프트웨어>금융 노드에 더존비즈온·웹캐시가 포함되어야 한다."""
        board = fixture_adapter.load("IT")
        sw = next(n for n in board.root.nodes if n.name == "소프트웨어")
        finance = next(n for n in sw.nodes if n.name == "금융")
        tickers = {s.ticker for s in finance.stocks}
        assert tickers == {"012510", "053580"}

    def test_list_fixture_boards(self, fixture_adapter):
        """fixtures/folder_mindmap/ 목록에 'IT'가 포함되어야 한다."""
        assert "IT" in fixture_adapter.list_boards()


class TestMutationFolderMindmap:
    """픽스처 복사본에서 load → 조작(추가/삭제/변경) → save → reload 검증."""

    def test_add_stock_to_internet(self, mutable_adapter, tmp_path):
        """인터넷 노드에 종목 추가 후 save하면 reload 시 반영되어야 한다."""
        board = mutable_adapter.load("IT")
        internet = next(n for n in board.root.nodes if n.name == "인터넷")
        internet.stocks.append(Stock(name="카카오뱅크", ticker="323410"))
        mutable_adapter.save(board)

        # 파일 존재 확인
        stock_file = (
            tmp_path / "folder_mindmap" / "IT" / "IT" / "인터넷" / "카카오뱅크.json"
        )
        assert stock_file.exists()

        # reload 후 종목 포함 확인
        reloaded = mutable_adapter.load("IT")
        internet_r = next(n for n in reloaded.root.nodes if n.name == "인터넷")
        tickers = {s.ticker for s in internet_r.stocks}
        assert "323410" in tickers
        assert len(tickers) == 4  # 기존 3개 + 1개

    def test_remove_stock_from_internet(self, mutable_adapter, tmp_path):
        """인터넷 노드에서 NAVER 종목 제거 후 save하면 reload 시 사라져야 한다."""
        board = mutable_adapter.load("IT")
        internet = next(n for n in board.root.nodes if n.name == "인터넷")
        internet.stocks = [s for s in internet.stocks if s.ticker != "035420"]
        mutable_adapter.save(board)

        # 파일 삭제 확인
        stock_file = (
            tmp_path / "folder_mindmap" / "IT" / "IT" / "인터넷" / "NAVER.json"
        )
        assert not stock_file.exists()

        # reload 후 종목 미포함 확인
        reloaded = mutable_adapter.load("IT")
        internet_r = next(n for n in reloaded.root.nodes if n.name == "인터넷")
        tickers = {s.ticker for s in internet_r.stocks}
        assert "035420" not in tickers
        assert len(tickers) == 2  # 기존 3개 - 1개

    def test_modify_stock_ticker(self, mutable_adapter, tmp_path):
        """네트워크 노드의 안랩 ticker 변경 후 save하면 reload 시 새 값이어야 한다."""
        board = mutable_adapter.load("IT")
        security = next(n for n in board.root.nodes if n.name == "보안")
        jeongbo = next(n for n in security.nodes if n.name == "정보보안")
        network = next(n for n in jeongbo.nodes if n.name == "네트워크")

        ahnlab = next(s for s in network.stocks if s.ticker == "053800")
        ahnlab.ticker = "AHNLAB_NEW"
        mutable_adapter.save(board)

        # reload 후 변경된 ticker 확인
        reloaded = mutable_adapter.load("IT")
        security_r = next(n for n in reloaded.root.nodes if n.name == "보안")
        jeongbo_r = next(n for n in security_r.nodes if n.name == "정보보안")
        network_r = next(n for n in jeongbo_r.nodes if n.name == "네트워크")
        tickers = {s.ticker for s in network_r.stocks}
        assert "AHNLAB_NEW" in tickers
        assert "053800" not in tickers
