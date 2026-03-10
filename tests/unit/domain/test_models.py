"""Stock, Node, Board 도메인 모델 단위 테스트."""

import pytest
from pydantic import ValidationError

from synapstock.domain.models import Board, Node, Stock


class TestStock:
    """Stock 모델 테스트."""

    def test_create_stock(self):
        """name과 ticker로 Stock이 정상 생성되어야 한다."""
        stock = Stock(name="삼성전자", ticker="005930")
        assert stock.name == "삼성전자"
        assert stock.ticker == "005930"

    def test_name_is_required(self):
        """name이 없으면 ValidationError가 발생해야 한다."""
        with pytest.raises(ValidationError):
            Stock(ticker="005930")  # type: ignore

    def test_ticker_is_required(self):
        """ticker가 없으면 ValidationError가 발생해야 한다."""
        with pytest.raises(ValidationError):
            Stock(name="삼성전자")  # type: ignore

    def test_model_dump(self):
        """Stock 인스턴스는 dict로 직렬화될 수 있어야 한다."""
        stock = Stock(name="카카오", ticker="035720")
        data = stock.model_dump()
        assert data == {"name": "카카오", "ticker": "035720"}

    def test_equality(self):
        """같은 name, ticker를 가진 두 Stock은 동일해야 한다."""
        s1 = Stock(name="NAVER", ticker="035420")
        s2 = Stock(name="NAVER", ticker="035420")
        assert s1 == s2


class TestNode:
    """Node 모델 테스트."""

    def test_add_child_increments_depth(self):
        """add_child()로 생성된 자식 노드는 부모 depth+1이어야 한다."""
        root = Node(name="root", depth=0)
        child = root.add_child("섹터A")
        assert child.depth == 1
        assert child in root.nodes

    def test_add_grandchild_depth(self):
        """손자 노드의 depth는 2이어야 한다."""
        root = Node(name="root", depth=0)
        child = root.add_child("섹터A")
        grandchild = child.add_child("소섹터1")
        assert grandchild.depth == 2

    def test_node_with_stocks(self):
        """Node에 Stock 목록을 추가할 수 있어야 한다."""
        stock = Stock(name="삼성전자", ticker="005930")
        node = Node(name="반도체", depth=1, stocks=[stock])
        assert len(node.stocks) == 1
        assert node.stocks[0].ticker == "005930"

    def test_recursive_structure_serialization(self):
        """재귀 트리 구조가 model_dump로 직렬화되어야 한다."""
        root = Node(name="root", depth=0)
        root.add_child("섹터A")
        data = root.model_dump()
        assert data["nodes"][0]["name"] == "섹터A"
        assert data["nodes"][0]["depth"] == 1

    def test_depth_is_required(self):
        """depth가 없으면 ValidationError가 발생해야 한다."""
        with pytest.raises(ValidationError):
            Node(name="root")  # type: ignore


class TestBoard:
    """Board 모델 테스트."""

    def test_create_board_auto_creates_root(self):
        """Board 생성 시 root 노드가 자동으로 만들어져야 한다."""
        board = Board(name="테마보드")
        assert board.root.name == "테마보드"
        assert board.root.depth == 0

    def test_root_starts_empty(self):
        """Board의 root 노드는 초기에 자식 노드와 종목을 가지지 않아야 한다."""
        board = Board(name="테마보드")
        assert board.root.nodes == []
        assert board.root.stocks == []

    def test_board_name_is_required(self):
        """name이 없으면 ValidationError가 발생해야 한다."""
        with pytest.raises(ValidationError):
            Board()  # type: ignore

    def test_board_root_tree_manipulation(self):
        """Board의 root를 시작점으로 트리를 만들 수 있어야 한다."""
        board = Board(name="테마보드")
        sector = board.root.add_child("섬터A")
        sector.stocks.append(Stock(name="삼성전자", ticker="005930"))

        assert len(board.root.nodes) == 1
        assert board.root.nodes[0].depth == 1
        assert board.root.nodes[0].stocks[0].ticker == "005930"
