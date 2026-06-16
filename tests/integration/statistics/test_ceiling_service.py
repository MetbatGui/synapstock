import pytest

from evenezer.infrastructure.container import container


@pytest.mark.asyncio


async def test_ceiling_service_full_workflow_integration():
    """상한가 분석 서비스의 전체 워크플로우(목록 조회 -> 동기화 -> 로컬 캐시) 통합 테스트."""
    # 1. 서비스 획득 (StatisticsService를 통한 접근)
    ceiling_svc = container.statistics_service.ceiling_svc
    repo = container.ceiling_repo

    # 2. 가용 연도 목록 조회
    years = await ceiling_svc.list_available_years()
    assert len(years) > 0
    print(f"\n[Test Result] 가용 연도: {years}")

    # 3. 최신 연도의 가용 날짜 목록 조회
    latest_year = years[0]
    dates = await ceiling_svc.list_available_dates(latest_year)
    assert len(dates) > 0
    print(f"[Test Result] {latest_year}년 가용 날짜 수: {len(dates)}")

    # 4. 최신 날짜로 실제 리포트 가져오기 (동기화 및 파싱 검증)
    test_date = dates[0]

    # 깨끗한 테스트를 위해 기존 캐시 잠시 제거 (선택적)
    import os
    json_path = repo.root / f"ceiling_{test_date}.json"
    if json_path.exists():
        os.remove(json_path)

    report = await ceiling_svc.get_ceiling_analysis(test_date, force_sync=True)

    assert report is not None
    assert report.end_date == test_date
    assert len(report.items) > 0
    assert json_path.exists(), "결과가 로컬 캐시(JSON)로 저장되어야 합니다."

    print(f"[Test Result] 리포트 조회 성공: {report.title}")
    print(f"기간: {report.start_date} ~ {report.end_date}")
    print(f"항목 수: {len(report.items)}")
    if report.items:
        print(f"샘플 항목: {report.items[0].name} ({report.items[0].entry_tag})")

@pytest.mark.asyncio

async def test_ceiling_cache_hit_integration():
    """드라이브 연결 없이 로컬 캐시에서 데이터를 정상적으로 가져오는지 확인."""
    ceiling_svc = container.statistics_service.ceiling_svc

    # 1. 캐시된 날짜 확인
    dates = await ceiling_svc.list_available_dates("2026")
    if not dates:
        pytest.skip("테스트를 위한 캐시 데이터가 없습니다.")

    test_date = dates[0]

    # 2. 드라이브 어댑터를 일시적으로 제거하여 캐시 히트 강제 확인
    original_adapter = ceiling_svc.drive_adapter
    ceiling_svc.drive_adapter = None

    try:
        report = await ceiling_svc.get_ceiling_analysis(test_date)
        assert report is not None
        assert report.end_date == test_date
        print(f"\n[Test Result] 캐시 히트 성공: {test_date}")
    finally:
        ceiling_svc.drive_adapter = original_adapter
