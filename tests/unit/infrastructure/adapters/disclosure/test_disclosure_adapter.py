import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from evenezer.infrastructure.adapters.disclosure.disclosure_adapter import DartDisclosureAdapter


@pytest.fixture
def mock_html_response():
    """DART 검색 결과 모의 HTML 응답."""
    return """
    <table>
        <tbody>
            <tr>
                <td>1</td>
                <td>삼성전자</td>
                <td><a href="#" onclick="openDisclosure('20260609000123')">반기보고서</a></td>
                <td>삼성전자</td>
                <td>2026.06.09</td>
            </tr>
            <tr>
                <td>2</td>
                <td>삼성전자</td>
                <td><a href="#" onclick="openDisclosure('20260609000456')">기업설명회</a></td>
                <td>삼성전자</td>
                <td>2026.06.09</td>
            </tr>
        </tbody>
    </table>
    """


class TestDartDisclosureAdapterCache:
    """DartDisclosureAdapter의 캐싱 기능 단위 테스트."""

    @patch("evenezer.infrastructure.adapters.disclosure.disclosure_adapter.requests.post")
    def test_caching_behavior(self, mock_post, mock_html_response):
        """동일한 종목을 여러 번 조회할 때 캐시가 작동하여 외부 요청을 한 번만 보내야 한다."""
        # Arrange
        mock_resp = MagicMock()
        mock_resp.text = mock_html_response
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        adapter = DartDisclosureAdapter()
        ticker = "005930"

        # Act - 1st call (캐시 없음, 네트워크 요청 발생해야 함)
        results1 = adapter.get_recent_disclosures(ticker)

        # Assert 1
        assert len(results1) == 2
        assert results1[0]["title"] == "반기보고서"
        assert results1[1]["rcpNo"] == "20260609000456"
        assert mock_post.call_count == 1

        # Act - 2nd call (동일 종목, 캐싱된 데이터 반환해야 함)
        results2 = adapter.get_recent_disclosures(ticker)

        # Assert 2 (네트워크 호출 횟수가 늘어나지 않아야 함)
        assert results2 == results1
        assert mock_post.call_count == 1

    @patch("evenezer.infrastructure.adapters.disclosure.disclosure_adapter.requests.post")
    def test_cache_expiration(self, mock_post, mock_html_response):
        """캐시 유지 시간(TTL)이 지나면 다시 외부 요청을 보내어 데이터를 갱신해야 한다."""
        # Arrange
        mock_resp = MagicMock()
        mock_resp.text = mock_html_response
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        adapter = DartDisclosureAdapter()
        ticker = "005930"

        # Act - 1st call (캐시 적재)
        adapter.get_recent_disclosures(ticker)
        assert mock_post.call_count == 1

        # 캐시 만료 시뮬레이션 (기존 캐시 엔트리의 만료 시간을 강제로 과거로 변환)
        cached_results, _ = adapter._cache[ticker]
        adapter._cache[ticker] = (cached_results, datetime.now() - timedelta(seconds=1))

        # Act - 2nd call (캐시가 만료되어 새로 네트워크 요청해야 함)
        adapter.get_recent_disclosures(ticker)
        
        # Assert (총 2회 호출 확인)
        assert mock_post.call_count == 2

    @patch("evenezer.infrastructure.adapters.disclosure.disclosure_adapter.requests.post")
    def test_clear_cache(self, mock_post, mock_html_response):
        """clear_cache 호출 시 기존 캐시가 적절히 파괴되어야 한다."""
        # Arrange
        mock_resp = MagicMock()
        mock_resp.text = mock_html_response
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        adapter = DartDisclosureAdapter()
        ticker1 = "005930"
        ticker2 = "000660"

        # 두 종목에 대해 캐시 적재
        adapter.get_recent_disclosures(ticker1)
        adapter.get_recent_disclosures(ticker2)
        assert mock_post.call_count == 2

        # 1. 특정 티커 캐시만 삭제 테스트
        adapter.clear_cache(ticker1)
        
        # ticker1 재요청 (캐시 없으므로 네트워크 요청 수행)
        adapter.get_recent_disclosures(ticker1)
        assert mock_post.call_count == 3

        # ticker2 재요청 (캐시 살아있으므로 네트워크 요청 증가 없음)
        adapter.get_recent_disclosures(ticker2)
        assert mock_post.call_count == 3

        # 2. 전체 캐시 삭제 테스트
        adapter.clear_cache()
        
        # ticker2 재요청 (캐시가 지워졌으므로 네트워크 요청 발생)
        adapter.get_recent_disclosures(ticker2)
        assert mock_post.call_count == 4
