"""Stock 도메인 모델 단위 테스트."""

import pytest
from pydantic import ValidationError

from synapstock.domain.models import Stock


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
