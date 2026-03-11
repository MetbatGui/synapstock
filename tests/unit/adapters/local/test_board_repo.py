"""LocalBoardRepository 단위 테스트."""

from pathlib import Path

import pytest

from synapstock.adapters.local.board_repo import LocalBoardRepository
from synapstock.domain.models import Board, Stock

FIXTURES_DIR = Path(__file__).parents[3] / "fixtures" / "boards"


@pytest.fixture
def repo(tmp_path):
    """임시 디렉터리 기반 LocalBoardRepository 픽스처 (쓰기 테스트용)."""
    return LocalBoardRepository(root_dir=tmp_path)


@pytest.fixture
def fixture_repo():
    """tests/fixtures/boards/ 기반 읽기 전용 LocalBoardRepository 픽스처."""
    return LocalBoardRepository(root_dir=FIXTURES_DIR)


@pytest.fixture
def simple_board() -> Board:
    """단순 보드 픽스처."""
    board = Board(name="테스트보드")
    sector = board.root.add_child("섹터A")
    sector.stocks.append(Stock(name="삼성전자", ticker="005930"))
    return board


class TestLocalBoardRepository:
    """LocalBoardRepository 기본 동작 테스트."""

    def test_save_creates_json_file(self, repo, simple_board, tmp_path):
        """save() 호출 시 JSON 파일이 생성되어야 한다."""
        repo.save(simple_board)
        assert (tmp_path / "테스트보드.json").exists()

    def test_save_and_load_roundtrip(self, repo, simple_board):
        """save 후 load하면 동일한 Board 구조여야 한다."""
        repo.save(simple_board)
        loaded = repo.load("테스트보드")

        assert loaded.name == simple_board.name
        assert loaded.root.name == simple_board.root.name
        assert loaded.root.depth == 0
        assert len(loaded.root.nodes) == 1
        assert loaded.root.nodes[0].name == "섹터A"
        assert loaded.root.nodes[0].stocks[0].ticker == "005930"

    def test_load_not_found(self, repo):
        """존재하지 않는 Board 로드 시 FileNotFoundError가 발생해야 한다."""
        with pytest.raises(FileNotFoundError, match="없는보드"):
            repo.load("없는보드")

    def test_list_boards_empty(self, repo):
        """저장된 Board가 없으면 빈 리스트를 반환해야 한다."""
        assert repo.list_boards() == []

    def test_list_boards(self, repo):
        """저장된 Board 이름 목록을 알파벳 정렬로 반환해야 한다."""
        repo.save(Board(name="B보드"))
        repo.save(Board(name="A보드"))
        repo.save(Board(name="C보드"))
        assert repo.list_boards() == ["A보드", "B보드", "C보드"]

    def test_save_overwrites_existing(self, repo):
        """같은 이름으로 다시 save()하면 덮어써야 한다."""
        board = Board(name="보드")
        repo.save(board)

        board.root.add_child("새섹터")
        repo.save(board)

        loaded = repo.load("보드")
        assert len(loaded.root.nodes) == 1
        assert loaded.root.nodes[0].name == "새섹터"

    def test_load_deep_tree(self, repo):
        """다층 트리 구조도 정확하게 복원되어야 한다."""
        board = Board(name="딥트리")
        child = board.root.add_child("D1")
        grandchild = child.add_child("D2")
        grandchild.stocks.append(Stock(name="테스트주", ticker="999999"))
        repo.save(board)

        loaded = repo.load("딥트리")
        assert loaded.root.nodes[0].nodes[0].depth == 2
        assert loaded.root.nodes[0].nodes[0].stocks[0].ticker == "999999"


class TestFixtureBoardRepository:
    """tests/fixtures/boards/ 기반 실제 파일 로드 테스트."""

    def test_load_it_board(self, fixture_repo):
        """IT.json을 로드하면 Board name이 'IT'이어야 한다."""
        board = fixture_repo.load("IT")
        assert board.name == "IT"
        assert board.root.name == "IT"
        assert board.root.depth == 0

    def test_it_board_top_level_nodes(self, fixture_repo):
        """IT 보드의 1depth 노드는 인터넷, 보안, 소프트웨어여야 한다."""
        board = fixture_repo.load("IT")
        names = [n.name for n in board.root.nodes]
        assert names == ["인터넷", "보안", "소프트웨어"]

    def test_it_board_internet_stocks(self, fixture_repo):
        """인터넷 노드에 NAVER(035420)가 포함되어 있어야 한다."""
        board = fixture_repo.load("IT")
        internet = board.root.nodes[0]
        tickers = [s.ticker for s in internet.stocks]
        assert "035420" in tickers

    def test_list_fixture_boards(self, fixture_repo):
        """fixtures/boards/ 목록에 'IT'가 포함되어야 한다."""
        assert "IT" in fixture_repo.list_boards()
