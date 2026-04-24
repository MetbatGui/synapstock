from pathlib import Path

import pytest

from synapstock.domain.statistics.models import CeilingAnalysisReport, CeilingItem
from synapstock.infrastructure.adapters.local.statistics_repo import LocalCeilingRepository


@pytest.fixture
def temp_ceiling_repo(tmp_path):
    """임시 디렉토리를 사용하는 상한가 저장소 피처."""
    return LocalCeilingRepository(data_root=str(tmp_path))

@pytest.mark.asyncio

async def test_save_and_load_ceiling_report(temp_ceiling_repo):
    # 1. 테스트 데이터 준비
    item = CeilingItem(
        name="테스트종목",
        entry_tag="상",
        closing_prices=[1000, 1100, 1200],
        change_rate=20.0,
        is_completed=False
    )
    report = CeilingAnalysisReport(
        title="테스트 리포트",
        start_date="2026-01-01",
        end_date="2026-01-05",
        items=[item],
        is_fully_collected=False
    )

    # 2. 저장
    temp_ceiling_repo.save_report(report)

    # 3. 파일 존재 확인
    expected_path = Path(temp_ceiling_repo.root) / "ceiling_2026-01-05.json"
    assert expected_path.exists()

    # 4. 조회 (특정 날짜)
    loaded = temp_ceiling_repo.load_report("2026-01-05")
    assert loaded is not None
    assert loaded.title == report.title
    assert len(loaded.items) == 1
    assert loaded.items[0].name == "테스트종목"

    # 5. 최신 리포트 조회
    latest = temp_ceiling_repo.load_latest_report()
    assert latest is not None
    assert latest.end_date == "2026-01-05"

@pytest.mark.asyncio

async def test_list_available_dates(temp_ceiling_repo):
    # 빈 데이터 확인
    assert temp_ceiling_repo.list_available_dates() == []

    # 여러 개 저장
    for date in ["2026-01-01", "2026-01-10", "2026-01-05"]:
        report = CeilingAnalysisReport(
            title=f"리포트_{date}",
            start_date="2026-01-01",
            end_date=date,
            items=[],
            is_fully_collected=True
        )
        temp_ceiling_repo.save_report(report)

    # 정렬된 날짜 목록 확인 (내림차순)
    dates = temp_ceiling_repo.list_available_dates()
    assert dates == ["2026-01-10", "2026-01-05", "2026-01-01"]
