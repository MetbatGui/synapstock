"""Board 도메인 모델 단위 테스트."""

import pytest
from pydantic import ValidationError

from evenezer.domain.models import Board, Node, Stock

# ── 픽스처 ──────────────────────────────────────────────────────────────────

@pytest.fixture
def it_board() -> Board:
    """IT 보드 픽스처: 인터넷 / 보안 / 소프트웨어 트리를 구성한다."""
    board = Board(name="IT")

    # 인터넷
    board.add_node("IT", "인터넷")
    board.add_stock_to_node("IT/인터넷", Stock(name="NAVER", ticker="035420"))
    board.add_stock_to_node("IT/인터넷", Stock(name="카카오", ticker="035720"))
    board.add_stock_to_node("IT/인터넷", Stock(name="이스트에이드", ticker="389240"))

    # 보안 / 정보보안
    board.add_node("IT", "보안")
    board.add_node("IT/보안", "정보보안")

    board.add_node("IT/보안/정보보안", "암호인증")
    board.add_stock_to_node("IT/보안/정보보안/암호인증", Stock(name="라온시큐어", ticker="042510"))
    board.add_stock_to_node("IT/보안/정보보안/암호인증", Stock(name="아톤", ticker="158430"))

    board.add_node("IT/보안/정보보안", "네트워크")
    board.add_stock_to_node("IT/보안/정보보안/네트워크", Stock(name="안랩", ticker="053800"))
    board.add_stock_to_node("IT/보안/정보보안/네트워크", Stock(name="윈스", ticker="136240"))
    board.add_stock_to_node("IT/보안/정보보안/네트워크", Stock(name="지니언스", ticker="263860"))

    board.add_node("IT/보안/정보보안", "보안관리")
    board.add_stock_to_node("IT/보안/정보보안/보안관리", Stock(name="이스트소프트", ticker="047560"))
    board.add_stock_to_node("IT/보안/정보보안/보안관리", Stock(name="샌즈랩", ticker="411080"))
    board.add_stock_to_node("IT/보안/정보보안/보안관리", Stock(name="모니터랩", ticker="323580"))

    board.add_node("IT/보안/정보보안", "정보 유출 방지")
    board.add_stock_to_node("IT/보안/정보보안/정보 유출 방지", Stock(name="지란지교시큐리티", ticker="208140"))
    board.add_stock_to_node("IT/보안/정보보안/정보 유출 방지", Stock(name="케이사인", ticker="192250"))
    board.add_stock_to_node("IT/보안/정보보안/정보 유출 방지", Stock(name="파수", ticker="150900"))

    # 보안 / 보안 서비스
    board.add_node("IT/보안", "보안 서비스")

    board.add_node("IT/보안/보안 서비스", "관제")
    board.add_stock_to_node("IT/보안/보안 서비스/관제", Stock(name="에스원", ticker="012750"))
    board.add_stock_to_node("IT/보안/보안 서비스/관제", Stock(name="이노뎁", ticker="303530"))

    board.add_node("IT/보안/보안 서비스", "장비")
    board.add_stock_to_node("IT/보안/보안 서비스/장비", Stock(name="아이디스", ticker="054800"))
    board.add_stock_to_node("IT/보안/보안 서비스/장비", Stock(name="포커스에이치엔에스", ticker="388050"))

    board.add_node("IT/보안/보안 서비스", "인증서")
    board.add_stock_to_node("IT/보안/보안 서비스/인증서", Stock(name="슈프리마", ticker="094840"))
    board.add_stock_to_node("IT/보안/보안 서비스/인증서", Stock(name="알체라", ticker="347860"))

    # 소프트웨어
    board.add_node("IT", "소프트웨어")

    board.add_node("IT/소프트웨어", "금융")
    board.add_stock_to_node("IT/소프트웨어/금융", Stock(name="더존비즈온", ticker="012510"))
    board.add_stock_to_node("IT/소프트웨어/금융", Stock(name="웹캐시", ticker="053580"))

    board.add_node("IT/소프트웨어", "업무")
    board.add_stock_to_node("IT/소프트웨어/업무", Stock(name="엠로", ticker="058970"))
    board.add_stock_to_node("IT/소프트웨어/업무", Stock(name="한글과컴퓨터", ticker="030520"))
    board.add_stock_to_node("IT/소프트웨어/업무", Stock(name="폴라리스오피스", ticker="041020"))

    board.add_node("IT/소프트웨어", "자동화")
    board.add_stock_to_node("IT/소프트웨어/자동화", Stock(name="링크제네시스", ticker="219480"))
    board.add_stock_to_node("IT/소프트웨어/자동화", Stock(name="비츠로시스", ticker="054220"))

    return board


# ── 기본 테스트 ──────────────────────────────────────────────────────────────

class TestBoard:
    """Board 기본 동작 테스트."""

    def test_auto_creates_root(self):
        """Board 생성 시 root 노드가 자동으로 만들어져야 한다."""
        board = Board(name="테마보드")
        assert board.root.name == "테마보드"
        assert board.root.depth == 0

    def test_root_starts_empty(self):
        """root 노드는 초기에 자식 노드와 종목을 가지지 않아야 한다."""
        board = Board(name="테마보드")
        assert "테마보드" in board.nodes
        assert len(board.nodes) == 1
        assert board.nodes["테마보드"].stocks == []

    def test_name_is_required(self):
        """name이 없으면 ValidationError가 발생해야 한다."""
        with pytest.raises(ValidationError):
            Board()  # type: ignore

    def test_board_find_node(self):
        """보드 내에서 절대 경로 또는 이름으로 노드를 검색한다."""
        board = Board(name="테마보드")
        board.add_node("테마보드", "섹터A")

        found = board.find_node("테마보드/섹터A")
        assert found is not None
        assert found.name == "섹터A"

    def test_board_add_node(self):
        """특정 노드 하위에 새 노드를 안전하게 추가한다."""
        board = Board(name="IT")
        board.add_node("IT", "인터넷")

        # 1. New node
        success = board.add_node("IT/인터넷", "포털")
        internet = board.find_node("IT/인터넷")
        assert success is True
        assert "IT/인터넷/포털" in board.nodes

        # 2. Duplicate
        success_dup = board.add_node("IT/인터넷", "포털")
        assert success_dup is True

    def test_board_delete_node_absorption(self):
        """노드 삭제 시 하위 요소들을 부모 노드로 흡수한다."""
        board = Board(name="Root")
        board.add_node("Root", "SectorA")
        board.add_node("Root/SectorA", "SubSector1")
        board.add_stock_to_node("Root/SectorA/SubSector1", Stock(name="Stock1", ticker="000001"))

        # Act
        success = board.delete_node("Root/SectorA/SubSector1")

        # Assert
        assert success is True
        assert board.find_node("Root/SectorA/SubSector1") is None
        sector = board.find_node("Root/SectorA")
        assert any(s.ticker == "000001" for s in sector.stocks)

    def test_board_delete_root_fails(self):
        """루트 노드는 삭제할 수 없어야 한다."""
        board = Board(name="IT")
        success = board.delete_node("IT")
        assert success is False
        assert board.root is not None
        assert board.root.name == "IT"

    def test_board_delete_stock(self):
        """Board 애그리게이트 루트를 통해 종목을 삭제할 수 있어야 한다."""
        board = Board(name="IT")
        board.add_node("IT", "인터넷")
        board.add_stock_to_node("IT/인터넷", Stock(name="카카오", ticker="035720"))

        assert board.find_stock("035720") is not None
        
        # 삭제 수행
        success = board.delete_stock("035720")
        assert success is True
        assert board.find_stock("035720") is None

    def test_board_report_management(self):
        """Board 애그리게이트 루트를 통해 종목에 리포트 링크를 추가하고 삭제할 수 있어야 한다."""
        board = Board(name="IT")
        board.add_node("IT", "인터넷")
        stock = Stock(name="카카오", ticker="035720")
        board.add_stock_to_node("IT/인터넷", stock)

        report_path = "data/pdf/kakao_report.pdf"

        # 리포트 추가
        success_add = board.add_report_to_stock("035720", report_path)
        assert success_add is True
        target_stock = board.find_stock("035720")
        assert report_path in target_stock.reports

        # 리포트 삭제
        success_remove = board.remove_report_from_stock("035720", report_path)
        assert success_remove is True
        assert report_path not in target_stock.reports


# ── IT 보드 트리 테스트 ───────────────────────────────────────────────────────

class TestITBoardTree:
    """IT 보드 복잡 트리 시나리오 테스트."""

    def test_root_depth_and_name(self, it_board: Board):
        """root는 depth=0이고 이름이 'IT'이어야 한다."""
        assert it_board.root.name == "IT"
        assert it_board.root.depth == 0

    def test_top_level_nodes(self, it_board: Board):
        """root 하위에 인터넷, 보안, 소프트웨어 3개 노드가 있어야 한다."""
        names = sorted([n.name for n in it_board.nodes.values() if n.parent_path == "IT"])
        assert names == sorted(["인터넷", "보안", "소프트웨어"])

    def test_internet_stocks(self, it_board: Board):
        """인터넷 노드에 NAVER, 카카오, 이스트에이드가 있어야 한다."""
        internet = it_board.nodes["IT/인터넷"]
        tickers = [s.ticker for s in internet.stocks]
        assert "035420" in tickers  # NAVER
        assert "035720" in tickers  # 카카오
        assert "389240" in tickers  # 이스트에이드

    def test_security_subtree_depth(self, it_board: Board):
        """보안 > 정보보안 > 암호인증의 depth가 각각 1, 2, 3이어야 한다."""
        security = it_board.nodes["IT/보안"]
        info_sec = it_board.nodes["IT/보안/정보보안"]
        enc = it_board.nodes["IT/보안/정보보안/암호인증"]
        assert security.depth == 1
        assert info_sec.depth == 2
        assert enc.depth == 3

    def test_network_security_stocks(self, it_board: Board):
        """네트워크 보안 노드에 안랩, 윈스, 지니언스가 있어야 한다."""
        net_sec = it_board.nodes["IT/보안/정보보안/네트워크"]
        tickers = [s.ticker for s in net_sec.stocks]
        assert "053800" in tickers  # 안랩
        assert "136240" in tickers  # 윈스
        assert "263860" in tickers  # 지니언스

    def test_software_subtree(self, it_board: Board):
        """소프트웨어 노드에 금융, 업무, 자동화 3개 서브 노드가 있어야 한다."""
        names = sorted([n.name for n in it_board.nodes.values() if n.parent_path == "IT/소프트웨어"])
        assert names == sorted(["금융", "업무", "자동화"])

    def test_software_finance_stocks(self, it_board: Board):
        """소프트웨어 > 금융에 더존비즈온, 웹캐시가 있어야 한다."""
        fin = it_board.nodes["IT/소프트웨어/금융"]
        tickers = [s.ticker for s in fin.stocks]
        assert "012510" in tickers  # 더존비즈온
        assert "053580" in tickers  # 웹캐시

    def test_print_full_tree(self, it_board: Board):
        """IT 보드 전체 트리를 출력한다 (pytest -s 시 확인 가능)."""
        print()
        print(it_board)
