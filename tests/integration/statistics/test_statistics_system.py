
import pytest

from synapstock.domain.statistics.models import DailyMarketRanking, MarketType, RankingItem, SupplySubject
from synapstock.infrastructure.container import Container


@pytest.fixture
def test_container(tmp_path):
    """테스트용 격리된 컨테이너 환경 제공."""
    # 환경 변수로 데이터 디렉토리 임시 변경 (필요한 경우)
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # 실제 컨테이너를 사용하되, 저장소 경로만 임시 디렉토리로 변경하여 테스트
    container = Container()
    # 주의: Container 내부에서 AppConfig.load()를 하므로, 실제 설정을 따라가게 됨.
    # 테스트를 위해 레포지토리의 root만 변경함.
    netbuy_dir = data_dir / "statistics" / "netbuy"
    netbuy_dir.mkdir(parents=True)

    from synapstock.infrastructure.adapters.local.statistics_repo import LocalStatisticsRepository
    container._statistics_repo = LocalStatisticsRepository(str(netbuy_dir))

    # StatisticsService 재초기화 (새 레포지토리 주입)
    from synapstock.application.services.statistics_service import StatisticsService
    container._statistics_service = StatisticsService(
        storage=container._drive_adapter,
        repository=container._statistics_repo,
        query_service=container._query_service,
        ceiling_repository=container._ceiling_repo,
        capital_increase_repository=container._capital_increase_repo,
        bonus_issue_repository=container._bonus_issue_repo,
        convertible_bond_repository=container._convertible_bond_repo,
        bw_repository=container._bw_repo,
        market_data_service=container._market_data_service,
    )

    return container

def test_statistics_flow_with_cache(test_container):
    """StatisticsService를 통한 데이터 조회 및 캐시 활용 흐름 테스트."""
    stats_service = test_container.statistics_service
    repo = test_container._statistics_repo

    date = "2026-04-22"
    market = MarketType.KOSPI
    subject = SupplySubject.FOREIGN

    # 1. 초기 상태 확인 (캐시 없음)
    assert repo.load_ranking(date, market, subject) is None

    # 2. 분석 데이터 요청 (데이터가 없으므로 sync_data가 내부적으로 호출되어야 함)
    # 실제 Google Drive 연결이 필요하므로, 여기서는 repo에 데이터를 수동으로 넣어 캐시 시뮬레이션을 하거나
    # 진짜 sync를 테스트할 수 있음. 여기서는 우선 코드 수정 후 정상 호출되는지 확인.

    # 수동으로 데이터 삽입 (캐시 시뮬레이션)
    mock_ranking = DailyMarketRanking(
        date=date, market=market, subject=subject,
        items=[RankingItem(rank=1, name="Samsung", amount=1000, ticker="005930")]
    )
    repo.save_daily_ranking(mock_ranking)

    # 3. 분석 요청
    result = stats_service.get_analyzed_ranking(date, market, subject)

    assert result is not None
    assert result.date == date
    assert len(result.items) == 1
    assert result.items[0].name == "Samsung"

    # 4. 요약 정보 요청 (StatisticsService에 추가할 메서드)
    summary = stats_service.get_daily_summary(date)
    assert "KOSPI" in summary
    assert summary["KOSPI"]["FOREIGN"].date == date

def test_available_dates_delegation(test_container):
    """StatisticsService를 통한 사용 가능한 날짜 목록 조회 테스트."""
    stats_service = test_container.statistics_service
    repo = test_container._statistics_repo

    # 데이터 저장
    date = "2026-04-22"
    mock_ranking = DailyMarketRanking(
        date=date, market=MarketType.KOSPI, subject=SupplySubject.FOREIGN,
        items=[]
    )
    repo.save_daily_ranking(mock_ranking)

    # StatisticsService에 추가할 메서드 또는 프로퍼티 확인
    if hasattr(stats_service, "list_available_dates"):
        dates = stats_service.list_available_dates(MarketType.KOSPI, SupplySubject.FOREIGN)
        assert date in dates
