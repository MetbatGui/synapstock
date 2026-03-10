"""Board 도메인 모델 단위 테스트."""

import pytest
from pydantic import ValidationError

from synapstock.domain.models import Board, Node, Stock


# ── 픽스처 ──────────────────────────────────────────────────────────────────

@pytest.fixture
def it_board() -> Board:
    """IT 보드 픽스처: 인터넷 / 보안 / 소프트웨어 트리를 구성한다."""
    board = Board(name="IT")

    # 인터넷
    internet = board.root.add_child("인터넷")
    internet.stocks = [
        Stock(name="NAVER", ticker="035420"),
        Stock(name="카카오", ticker="035720"),
        Stock(name="이스트에이드", ticker="389240"),
    ]

    # 보안 / 정보보안
    security = board.root.add_child("보안")
    info_sec = security.add_child("정보보안")

    enc = info_sec.add_child("암호인증")
    enc.stocks = [Stock(name="라온시큐어", ticker="042510"), Stock(name="아톤", ticker="158430")]

    net_sec = info_sec.add_child("네트워크")
    net_sec.stocks = [
        Stock(name="안랩", ticker="053800"),
        Stock(name="윈스", ticker="136240"),
        Stock(name="지니언스", ticker="263860"),
    ]

    mgmt = info_sec.add_child("보안관리")
    mgmt.stocks = [
        Stock(name="이스트소프트", ticker="047560"),
        Stock(name="샌즈랩", ticker="411080"),
        Stock(name="모니터랩", ticker="323580"),
    ]

    dlp = info_sec.add_child("정보 유출 방지")
    dlp.stocks = [
        Stock(name="지란지교시큐리티", ticker="208140"),
        Stock(name="케이사인", ticker="192250"),
        Stock(name="파수", ticker="150900"),
    ]

    # 보안 / 보안 서비스
    sec_svc = security.add_child("보안 서비스")

    ctrl = sec_svc.add_child("관제")
    ctrl.stocks = [Stock(name="에스원", ticker="012750"), Stock(name="이노뎁", ticker="303530")]

    equip = sec_svc.add_child("장비")
    equip.stocks = [Stock(name="아이디스", ticker="054800"), Stock(name="포커스에이치엔에스", ticker="PortFocus")]

    auth_node = sec_svc.add_child("인증서")
    auth_node.stocks = [Stock(name="슈프리마", ticker="094840"), Stock(name="알체라", ticker="347860")]

    # 소프트웨어
    software = board.root.add_child("소프트웨어")

    fin = software.add_child("금융")
    fin.stocks = [Stock(name="더존비즈온", ticker="012510"), Stock(name="웹캐시", ticker="053580")]

    biz = software.add_child("업무")
    biz.stocks = [
        Stock(name="엠로", ticker="058970"),
        Stock(name="한글과컴퓨터", ticker="030520"),
        Stock(name="폴라리스오피스", ticker="041020"),
    ]

    auto = software.add_child("자동화")
    auto.stocks = [Stock(name="링크제네시스", ticker="219480"), Stock(name="비츠로시스", ticker="054220")]

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
        assert board.root.nodes == []
        assert board.root.stocks == []

    def test_name_is_required(self):
        """name이 없으면 ValidationError가 발생해야 한다."""
        with pytest.raises(ValidationError):
            Board()  # type: ignore

    def test_tree_manipulation(self):
        """root를 시작점으로 트리를 만들 수 있어야 한다."""
        board = Board(name="테마보드")
        sector = board.root.add_child("섹터A")
        sector.stocks.append(Stock(name="삼성전자", ticker="005930"))

        assert len(board.root.nodes) == 1
        assert board.root.nodes[0].depth == 1
        assert board.root.nodes[0].stocks[0].ticker == "005930"


# ── IT 보드 트리 테스트 ───────────────────────────────────────────────────────

class TestITBoardTree:
    """IT 보드 복잡 트리 시나리오 테스트."""

    def test_root_depth_and_name(self, it_board: Board):
        """root는 depth=0이고 이름이 'IT'이어야 한다."""
        assert it_board.root.name == "IT"
        assert it_board.root.depth == 0

    def test_top_level_nodes(self, it_board: Board):
        """root 하위에 인터넷, 보안, 소프트웨어 3개 노드가 있어야 한다."""
        names = [n.name for n in it_board.root.nodes]
        assert names == ["인터넷", "보안", "소프트웨어"]

    def test_internet_stocks(self, it_board: Board):
        """인터넷 노드에 NAVER, 카카오, 이스트에이드가 있어야 한다."""
        internet = it_board.root.nodes[0]
        tickers = [s.ticker for s in internet.stocks]
        assert "035420" in tickers  # NAVER
        assert "035720" in tickers  # 카카오
        assert "389240" in tickers  # 이스트에이드

    def test_security_subtree_depth(self, it_board: Board):
        """보안 > 정보보안 > 암호인증의 depth가 각각 1, 2, 3이어야 한다."""
        security = it_board.root.nodes[1]
        info_sec = security.nodes[0]          # 정보보안
        enc = info_sec.nodes[0]               # 암호인증
        assert security.depth == 1
        assert info_sec.depth == 2
        assert enc.depth == 3

    def test_network_security_stocks(self, it_board: Board):
        """네트워크 보안 노드에 안랩, 윈스, 지니언스가 있어야 한다."""
        info_sec = it_board.root.nodes[1].nodes[0]   # 보안 > 정보보안
        net_sec = info_sec.nodes[1]                   # 네트워크
        tickers = [s.ticker for s in net_sec.stocks]
        assert "053800" in tickers  # 안랩
        assert "136240" in tickers  # 윈스
        assert "263860" in tickers  # 지니언스

    def test_software_subtree(self, it_board: Board):
        """소프트웨어 노드에 금융, 업무, 자동화 3개 서브 노드가 있어야 한다."""
        software = it_board.root.nodes[2]
        names = [n.name for n in software.nodes]
        assert names == ["금융", "업무", "자동화"]

    def test_software_finance_stocks(self, it_board: Board):
        """소프트웨어 > 금융에 더존비즈온, 웹캐시가 있어야 한다."""
        fin = it_board.root.nodes[2].nodes[0]
        tickers = [s.ticker for s in fin.stocks]
        assert "012510" in tickers  # 더존비즈온
        assert "053580" in tickers  # 웹캐시

    def test_print_full_tree(self, it_board: Board):
        """IT 보드 전체 트리를 출력한다 (pytest -s 시 확인 가능)."""

        def print_tree(node: Node, indent: int = 0) -> None:
            prefix = "  " * indent
            print(f"{prefix}[D{node.depth}] {node.name}")
            for stock in node.stocks:
                print(f"{prefix}  - {stock.name} ({stock.ticker})")
            for child in node.nodes:
                print_tree(child, indent + 1)

        print()  # 줄바꿈으로 테스트 헤더와 분리
        print_tree(it_board.root)
