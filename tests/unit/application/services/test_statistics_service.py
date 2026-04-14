import pytest
from unittest.mock import MagicMock
from synapstock.application.services.statistics_service import StatisticsService

@pytest.fixture
def mock_query_service():
    return MagicMock()

@pytest.fixture
def service(mock_query_service):
    return StatisticsService(
        query_service=mock_query_service,
        storage=MagicMock(),
        repository=MagicMock(),
        ceiling_repository=MagicMock()
    )

class TestStatisticsService:
    """StatisticsService 단위 테스트."""

    def test_build_local_ticker_map_with_aliases(self, service, mock_query_service):
        """티커 맵 빌드 시 종목의 별칭(aliases)도 모두 매핑에 포함되어야 한다."""
        # Arrange: 별칭이 있는 종목과 없는 종목 준비
        mock_query_service.get_all_stocks_flat.return_value = [
            {
                "name": "LIG디펜스앤에어로스페이스",
                "ticker": "079550",
                "aliases": ["LIG넥스원"]
            },
            {
                "name": "삼성전자",
                "ticker": "005930",
                "aliases": []
            }
        ]

        # Act
        ticker_map = service._build_local_ticker_map()

        # Assert
        # 1. 정식 명칭 매핑 확인
        assert ticker_map["LIG디펜스앤에어로스페이스"] == "079550"
        assert ticker_map["삼성전자"] == "005930"
        
        # 2. 별칭 매핑 확인
        assert ticker_map["LIG넥스원"] == "079550"
        
        # 3. 전체 개수 확인 (정식 2개 + 별칭 1개 = 3개)
        assert len(ticker_map) == 3

    def test_build_local_ticker_map_empty(self, service, mock_query_service):
        """종목이 없는 경우 빈 맵을 반환해야 한다."""
        mock_query_service.get_all_stocks_flat.return_value = []
        ticker_map = service._build_local_ticker_map()
        assert ticker_map == {}
