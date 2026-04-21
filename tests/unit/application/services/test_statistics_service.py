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
        ceiling_repository=MagicMock(),
        capital_increase_repository=MagicMock(),
        bonus_issue_repository=MagicMock(),
        convertible_bond_repository=MagicMock(),
        market_data_service=MagicMock()
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

    def test_normalize_item_name(self, service, mock_query_service):
        """별칭(LIG넥스원)이 들어왔을 때 정규 사명(LIG디펜스앤에어로스페이스)으로 치환되어야 한다."""
        from synapstock.domain.statistics.models import RankingItem
        
        # Arrange
        item = RankingItem(rank=1, name="LIG넥스원", amount=1000, ticker=None)
        mock_query_service.search_ticker.return_value = [
            {"name": "LIG디펜스앤에어로스페이스", "ticker": "079550"}
        ]
        
        # Act
        service._normalize_item_name(item)
        
        # Assert
        assert item.name == "LIG디펜스앤에어로스페이스"
        assert item.ticker == "079550"
        mock_query_service.search_ticker.assert_called_once_with("LIG넥스원")

    def test_normalize_item_name_lowercase(self, service, mock_query_service):
        """소문자 별칭(lig넥스원)이 들어왔을 때도 정규 사명으로 치환되어야 한다."""
        from synapstock.domain.statistics.models import RankingItem
        
        # Arrange
        item = RankingItem(rank=1, name="lig넥스원", amount=500, ticker=None)
        # 실제 NaverTickerSearchAdapter는 내부에서 정규화를 수행하여 반환함
        mock_query_service.search_ticker.return_value = [
            {"name": "LIG디펜스앤에어로스페이스", "ticker": "079550"}
        ]
        
        # Act
        service._normalize_item_name(item)
        
        # Assert
        assert item.name == "LIG디펜스앤에어로스페이스"
        assert item.ticker == "079550"

    def test_sync_convertible_bond_data_success(self, service, mock_query_service):
        """구글 드라이브에서 파일을 가져와 파싱하고 티커 정보를 보강하여 저장해야 한다."""
        from synapstock.domain.statistics.models import ConvertibleBond

        # Arrange: 모킹 설정
        mock_storage = service._storage
        mock_repo = service._convertible_bond_repo
        
        # 1. 파일 목록 모킹
        mock_storage.list_files_in_folder.return_value = [
            {"name": "2026_CB_Analysis.xlsx"}
        ]
        mock_storage.get_file.return_value = b"fake_excel_content"

        # 2. 파서 결과 모킹 (티커가 없는 상태)
        mock_items = [
            ConvertibleBond(date="2026-01-01", name="삼성전자", bond_amount=1000, rcp_no="1"),
            ConvertibleBond(date="2026-01-02", name="현대차", bond_amount=2000, rcp_no="2")
        ]
        service._parser.parse_convertible_bond = MagicMock(return_value=mock_items)

        # 3. 티커 맵 모킹
        mock_query_service.get_all_stocks_flat.return_value = [
            {"name": "삼성전자", "ticker": "005930", "aliases": []},
            {"name": "현대차", "ticker": "005380", "aliases": []}
        ]

        # Act
        result = service.sync_convertible_bond_data()

        # Assert
        assert len(result) == 2
        assert result[0].ticker == "005930"
        assert result[1].ticker == "005380"
        
        # 저장소 호출 확인
        mock_repo.save_data.assert_called_once_with(result)
        mock_storage.get_file.assert_called_once_with("2026_CB_Analysis.xlsx", folder="convertible_bond")

    def test_get_convertible_bond_data_caching(self, service):
        """캐시가 있으면 동기화 없이 캐시를 반환하고, 없으면 동기화를 수행해야 한다."""
        from synapstock.domain.statistics.models import ConvertibleBond
        mock_repo = service._convertible_bond_repo
        
        # 1. 캐시가 있는 경우
        cached_data = [ConvertibleBond(date="2026-01-01", name="캐시종목", bond_amount=100, rcp_no="c1")]
        mock_repo.load_data.return_value = cached_data
        
        service.sync_convertible_bond_data = MagicMock()
        
        result = service.get_convertible_bond_data()
        
        assert result == cached_data
        service.sync_convertible_bond_data.assert_not_called()

        # 2. 캐시가 없는 경우
        mock_repo.load_data.return_value = []
        sync_result = [ConvertibleBond(date="2026-01-01", name="동기종목", bond_amount=200, rcp_no="s1")]
        service.sync_convertible_bond_data.return_value = sync_result
        
        result = service.get_convertible_bond_data()
        
        assert result == sync_result
        service.sync_convertible_bond_data.assert_called_once()
