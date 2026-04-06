"""Stock, Node 도메인 모델 단위 테스트."""

import pytest
from pydantic import ValidationError

from synapstock.domain.models import Node, Stock


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
        assert data == {
            "name": "카카오",
            "ticker": "035720",
            "news": [],
            "reports": []
        }

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

    def test_node_find_node_recursive(self):
        """이름으로 하위 노드를 재귀적으로 검색한다.

        Arrange:
            root -> child -> grandchild 구조를 생성한다.
        Act:
            root.find_node("grandchild")를 호출한다.
        Assert:
            검색 결과가 실제 grandchild 객체와 동일한지 확인한다.
        """
        root = Node(name="root", depth=0)
        child = root.add_child("child")
        grandchild = child.add_child("grandchild")

        found = root.find_node("grandchild")
        
        assert found is grandchild
        assert found.name == "grandchild"

    def test_node_add_stock_duplication_check(self):
        """중복된 티커를 가진 종목 추가를 방지한다.

        Arrange:
            종목 "S1"을 가진 노드를 준비한다.
        Act:
            동일한 티커 "S1"을 가진 다른 종목 객체를 추가한다.
        Assert:
            종목 리스트의 길이가 여전히 1인지 확인한다.
        """
        node = Node(name="sector", depth=1)
        node.add_stock(Stock(name="Stock1", ticker="S1"))
        
        node.add_stock(Stock(name="Stock1_Dup", ticker="S1"))
        
        assert len(node.stocks) == 1
        assert node.stocks[0].name == "Stock1"

    def test_node_find_and_remove_stock(self):
        """재귀적으로 하위 노드에서 종목을 찾아 삭제한다.

        Arrange:
            root -> child 하위에 종목 "S1"을 추가한다.
        Act:
            root.find_and_remove_stock("S1")을 호출한다.
        Assert:
            child의 종목 리스트가 비어있는지 확인한다.
        """
        root = Node(name="root", depth=0)
        child = root.add_child("child")
        child.add_stock(Stock(name="Stock1", ticker="S1"))
        
        success = root.find_and_remove_stock("S1")
        
        assert success is True
        assert len(child.stocks) == 0

    def test_node_news_management_recursive(self):
        """재귀적으로 종목을 찾아 뉴스를 추가 및 삭제한다.

        Arrange:
            깊은 노드에 종목 "S1"이 있는 트리를 생성한다.
        Act:
            1. find_and_add_news로 뉴스 추가.
            2. find_and_remove_news로 뉴스 삭제.
        Assert:
            추가 후 뉴스 리스트 길이는 1, 삭제 후 0인지 확인한다.
        """
        root = Node(name="root", depth=0)
        child = root.add_child("child")
        stock = Stock(name="Stock1", ticker="S1")
        child.add_stock(stock)
        
        news = {"title": "Title", "date": "2024-01-01", "url": "http://test.com"}
        
        # Add
        root.find_and_add_news("S1", news)
        assert len(child.stocks[0].news) == 1
        
        # Remove
        root.find_and_remove_news("S1", "http://test.com")
        assert len(child.stocks[0].news) == 0

    def test_node_report_management_recursive(self):
        """재귀적으로 종목을 찾아 리포트 경로를 추가 및 삭제한다.

        Arrange:
            깊은 노드에 종목 "S1"이 있는 트리를 생성한다.
        Act:
            1. find_and_add_report로 경로 추가.
            2. find_and_remove_report로 경로 삭제.
        Assert:
            추가 후 리포트 리스트 길이는 1, 삭제 후 0인지 확인한다.
        """
        root = Node(name="root", depth=0)
        child = root.add_child("child")
        stock = Stock(name="Stock1", ticker="S1")
        child.add_stock(stock)
        
        report_path = "data/pdf/report1.pdf"
        
        # Add
        root.find_and_add_report("S1", report_path)
        assert len(child.stocks[0].reports) == 1
        
        # Remove
        root.find_and_remove_report("S1", report_path)
        assert len(child.stocks[0].reports) == 0

