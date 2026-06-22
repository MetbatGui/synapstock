"""Stock, Node 도메인 모델 단위 테스트."""

import pytest
from pydantic import ValidationError

from evenezer.domain.models import Node, Stock


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
            "aliases": [],
            "news": [],
            "reports": []
        }

    def test_equality(self):
        """같은 name, ticker를 가진 두 Stock은 동일해야 한다."""
        s1 = Stock(name="NAVER", ticker="035420")
        s2 = Stock(name="NAVER", ticker="035420")
        assert s1 == s2

    def test_stock_with_aliases(self):
        """별칭(aliases)을 가진 Stock이 정상 생성되어야 한다."""
        stock = Stock(name="사명변경후", ticker="123456", aliases=["옛날사명", "다른이름"])
        assert "옛날사명" in stock.aliases
        assert "다른이름" in stock.aliases
        assert len(stock.aliases) == 2

    def test_serialization_excludes_empty_aliases(self):
        """별칭이 비어있는 경우 직렬화(JSON) 시 해당 필드가 제외되어야 한다 (exclude_defaults=True)."""
        stock = Stock(name="삼성전자", ticker="005930")
        # aliases 기본값은 [] 이므로 exclude_defaults=True 시 제외됨
        data = stock.model_dump(exclude_defaults=True)
        assert "aliases" not in data
        assert "news" not in data
        assert "reports" not in data
        assert data["name"] == "삼성전자"

        # 별칭이 있는 경우는 포함되어야 함
        stock_with_alias = Stock(name="LIG디펜스앤에어로스페이스", ticker="079550", aliases=["LIG넥스원"])
        data_with_alias = stock_with_alias.model_dump(exclude_defaults=True)
        assert "aliases" in data_with_alias
        assert data_with_alias["aliases"] == ["LIG넥스원"]

    def test_validate_ticker_fail(self):
        """유효하지 않은 티커 형식(알파벳/숫자가 아니거나 길이가 1~12자리가 아닌 경우)이면 ValidationError가 발생해야 한다."""
        with pytest.raises(ValidationError) as exc_info:
            Stock(name="삼성전자", ticker="A" * 13)  # 13자리
        assert "1~12자리 알파뉴메릭 구조여야 함" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            Stock(name="삼성전자", ticker="00593#")  # 특수문자 포함
        assert "1~12자리 알파뉴메릭 구조여야 함" in str(exc_info.value)

    def test_matches_query(self):
        """matches()가 종목명 및 별칭 매칭을 대소문자 무관하게 잘 수행하는지 확인한다."""
        stock = Stock(name="NAVER", ticker="035420", aliases=["네이버", "네이바"])
        
        # 종목명 매칭 (대소문자 무관)
        assert stock.matches("naver") is True
        assert stock.matches("Nav") is True
        assert stock.matches("NAV") is True
        
        # 별칭 매칭
        assert stock.matches("네이버") is True
        assert stock.matches("네이") is True
        
        # 매칭 실패
        assert stock.matches("kakao") is False

    def test_has_valid_ticker(self):
        """has_valid_ticker가 유효성을 정확히 판단하는지 확인한다."""
        s_valid = Stock(name="삼성전자", ticker="005930")
        assert s_valid.has_valid_ticker is True

        s_valid_alnum = Stock(name="채비", ticker="0011T0")
        assert s_valid_alnum.has_valid_ticker is True

        s_invalid_len = Stock(name="에러", ticker="123456")
        s_invalid_len.ticker = "12345"  # 5자리
        assert s_invalid_len.has_valid_ticker is False

        s_invalid_char = Stock(name="에러", ticker="123456")
        s_invalid_char.ticker = "12345#"  # 특수문자 포함
        assert s_invalid_char.has_valid_ticker is False

    def test_rename(self):
        """rename() 호출 시 이름이 바뀌고 기존 이름이 aliases에 들어가는지 확인한다."""
        stock = Stock(name="삼성전자", ticker="005930", aliases=["삼전"])
        stock.rename("삼성전자")  # 이름이 같을 때
        assert stock.name == "삼성전자"
        assert stock.aliases == ["삼전"]

        stock.rename("새삼성")  # 이름이 다를 때
        assert stock.name == "새삼성"
        assert "삼성전자" in stock.aliases
        assert "삼전" in stock.aliases
        assert len(stock.aliases) == 2


class TestNode:
    """Node 모델 테스트."""

    def test_create_node(self):
        """Node 생성 시 parent_path 및 기본 필드들이 유효해야 한다."""
        node = Node(name="반도체", depth=1, parent_path="Theme_IT")
        assert node.name == "반도체"
        assert node.depth == 1
        assert node.parent_path == "Theme_IT"
        assert node.stocks == []

    def test_node_with_stocks(self):
        """Node에 Stock 목록을 추가할 수 있어야 한다."""
        stock = Stock(name="삼성전자", ticker="005930")
        node = Node(name="반도체", depth=1, stocks=[stock])
        assert len(node.stocks) == 1
        assert node.stocks[0].ticker == "005930"

    def test_depth_is_required(self):
        """depth가 없으면 ValidationError가 발생해야 한다."""
        with pytest.raises(ValidationError):
            Node(name="root")  # type: ignore

    def test_node_add_stock_duplication_check(self):
        """중복된 티커를 가진 종목 추가를 방지한다."""
        node = Node(name="sector", depth=1)
        node.add_stock(Stock(name="Stock1", ticker="000001"))
        node.add_stock(Stock(name="Stock1_Dup", ticker="000001"))

        assert len(node.stocks) == 1
        assert node.stocks[0].name == "Stock1"

    def test_node_remove_stock(self):
        """티커로 종목을 찾아 삭제한다."""
        node = Node(name="sector", depth=1)
        node.add_stock(Stock(name="Stock1", ticker="000001"))
        success = node.remove_stock("000001")
        assert success is True
        assert len(node.stocks) == 0

