import pytest
from unittest.mock import MagicMock

from evenezer.application.services.financial_service import FinancialService
from evenezer.domain.statistics.models import MarketType


class MockStatement:
    def __init__(self, stock_name, values):
        self.stock_name = stock_name
        self.values = values


def test_consecutive_growers_zero_division_skip():
    """get_consecutive_growers 호출 시 분모(이전 값)가 0인 종목이 ZeroDivisionError를 유발하지 않고 정상적으로 스킵되는지 검증."""
    # Arrange
    mock_repo = MagicMock()
    
    # metrics의 최신 분기를 리턴
    mock_repo.get_latest_quarter.return_value = "2026.1Q"
    
    # 2분기 연속 성장주를 위해 needed_count = count(2) + 2 = 4개 분기 필요:
    # 2026.1Q, 2025.4Q, 2025.3Q, 2025.2Q
    # vals 리스트: [vals[0], vals[1], vals[2], vals[3]] -> [2025.2Q, 2025.3Q, 2025.4Q, 2026.1Q]
    # vals[1] (prev_value)가 0.0 인 종목을 준비하여 ZeroDivision 방어 테스트 수행
    statements = [
        # 1. 분모가 0.0 인 종목
        MockStatement("제로나누기기업", {
            "2026.1Q": 300.0,
            "2025.4Q": 200.0,
            "2025.3Q": 0.0,      # vals[1] = 0.0
            "2025.2Q": 50.0
        }),
        # 2. 정상 성장 종목
        MockStatement("정상성장기업", {
            "2026.1Q": 300.0,
            "2025.4Q": 200.0,
            "2025.3Q": 100.0,     # vals[1] = 100.0 (0.0 이 아님)
            "2025.2Q": 50.0
        })
    ]
    mock_repo.load_all.return_value = statements
    
    service = FinancialService(repository=mock_repo)
    
    # Act
    # count=2 (2분기 연속 성장 조회)
    result = service.get_consecutive_growers(metric="OPERATING_PROFIT", target_quarter="2026.1Q", count=2)
    
    # Assert
    # 에러 없이 정상 실행되어야 하며, "제로나누기기업"은 스킵되고 "정상성장기업"만 통과해야 함
    assert "normal" in result
    normal_list = result["normal"]
    
    assert len(normal_list) == 1
    assert normal_list[0].stock_name == "정상성장기업"
    assert normal_list[0].change_rate > 0
