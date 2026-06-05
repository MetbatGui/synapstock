from unittest.mock import AsyncMock, MagicMock

import pytest

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
        bw_repository=MagicMock()
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

    def test_enrich_tickers(self, service, mock_query_service):
        """_enrich_tickers를 통해 아이템 리스트의 티커가 보강되어야 한다."""
        from synapstock.domain.statistics.models import RankingItem

        # Arrange
        mock_query_service.get_all_stocks_flat.return_value = [
            {"name": "LIG디펜스앤에어로스페이스", "ticker": "079550", "aliases": ["LIG넥스원"]},
            {"name": "삼성전자", "ticker": "005930", "aliases": []}
        ]

        items = [
            RankingItem(rank=1, name="LIG넥스원", amount=1000, ticker=None),
            RankingItem(rank=2, name="삼성전자", amount=500, ticker=None)
        ]

        # Act
        enriched_items = service._enrich_tickers(items)

        # Assert
        assert enriched_items[0].ticker == "079550"
        assert enriched_items[1].ticker == "005930"

    @pytest.mark.asyncio
    async def test_get_convertible_bond_data_delegation(self, service):
        """CB 데이터 조회 시 disclosure_svc에 위임하고 티커를 보강해야 한다."""
        from synapstock.domain.statistics.models import ConvertibleBond

        # Arrange
        mock_disclosure_svc = MagicMock()
        mock_disclosure_svc.get_data = AsyncMock()
        service.disclosure_svc = mock_disclosure_svc

        mock_items = [
            ConvertibleBond(date="2026-01-01", name="삼성전자", bond_amount=1000, rcp_no="1")
        ]
        mock_disclosure_svc.get_data.return_value = mock_items
        service._enrich_tickers = MagicMock(return_value=mock_items)

        # Act
        result = await service.get_convertible_bond_data(force_sync=True, year="2026")

        # Assert
        mock_disclosure_svc.get_data.assert_called_once_with("cb", "2026", force_sync=True)
        service._enrich_tickers.assert_called_once_with(mock_items)
        assert result == mock_items

    @pytest.mark.asyncio
    async def test_get_bw_data_delegation(self, service):
        """BW 데이터 조회 시 disclosure_svc에 위임하고 티커를 보강해야 한다."""
        from synapstock.domain.statistics.models import BondWithWarrants

        # Arrange
        mock_disclosure_svc = MagicMock()
        mock_disclosure_svc.get_data = AsyncMock()
        service.disclosure_svc = mock_disclosure_svc

        mock_items = [
            BondWithWarrants(date="2026-01-05", name="오텍", rcp_no="bw1", bond_amount=20000000000)
        ]
        mock_disclosure_svc.get_data.return_value = mock_items
        service._enrich_tickers = MagicMock(return_value=mock_items)

        # Act
        result = await service.get_bw_data(force_sync=False, year="2026")

        # Assert
        mock_disclosure_svc.get_data.assert_called_once_with("bw", "2026", force_sync=False)
        service._enrich_tickers.assert_called_once_with(mock_items)
        assert result == mock_items
