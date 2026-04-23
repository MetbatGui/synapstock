import pytest
from synapstock.infrastructure.parsers.excel.base import BaseExcelParser

class ConcreteParser(BaseExcelParser):
    def parse(self, content, **kwargs):
        return None

@pytest.fixture
def parser():
    return ConcreteParser()

def test_clean_stock_name(parser):
    assert parser._clean_stock_name("삼성전자 (쌍)") == "삼성전자"
    assert parser._clean_stock_name("현대차(상)") == "현대차"
    assert parser._clean_stock_name(" LG에너지솔루션 (씽) ") == "LG에너지솔루션"
    assert parser._clean_stock_name("SK하이닉스") == "SK하이닉스"

def test_to_int(parser):
    assert parser.to_int(1000) == 1000
    assert parser.to_int("1,000") == 1000
    assert parser.to_int("75,000백만원") == 75000
    assert parser.to_int("-") == 0
    assert parser.to_int(None) == 0

def test_to_float(parser):
    assert parser.to_float(32.33) == 32.33
    assert parser.to_float("32.33%") == 32.33
    assert parser.to_float("650:1") == 650.0
    assert parser.to_float("1,234.56") == 1234.56
    assert parser.to_float("-") == 0.0

def test_to_str(parser):
    import pandas as pd
    assert parser.to_str(" Hello ") == "Hello"
    assert parser.to_str(pd.Timestamp("2026-04-22")) == "2026-04-22"
    assert parser.to_str(None) == ""

def test_format_date(parser):
    assert parser._format_date("2026.04.22") == "2026-04-22"
    assert parser._format_date("260422") == "2026-04-22"
    assert parser._format_date("20260422") == "2026-04-22"
    assert parser._format_date(None) == ""
