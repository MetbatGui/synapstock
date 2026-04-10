import pytest
from synapstock.infrastructure.container import container
from synapstock.application.services.statistics_service import StatisticsService
from synapstock.domain.statistics.models import CeilingAnalysisReport

def test_get_ceiling_analysis_service_integration():
    """StatisticsService를 통해 상한가 분석 데이터를 온디맨드로 가져오는 통합 테스트."""
    
    # 1. 서비스 획득
    service = container.statistics_service
    repo = container.ceiling_repo
    
    # 테스트 날짜 (4월 중 하루)
    test_date = "2026-04-10"
    
    # 2. 기존 캐시가 있다면 삭제 (깨끗한 테스트를 위해)
    # 실제 환경에서는 삭제하지 않으나 테스트 목적상 강제 동기화 흐름 확인용
    import os
    json_path = repo.root / f"ceiling_{test_date}.json"
    if json_path.exists():
        os.remove(json_path)
    
    # 3. 서비스 호출 (최초 호출 - 드라이브 접속 및 파싱 발생)
    report = service.get_ceiling_analysis(test_date)
    
    assert report is not None
    assert report.end_date == test_date
    assert len(report.items) > 0
    assert json_path.exists(), "결과가 로컬 캐시(JSON)로 저장되어야 합니다."
    
    # 4. 두 번째 호출 (캐시 히트 확인)
    # 드라이브 어댑터를 일시적으로 None으로 설정해도 캐시에서 가져와야 함
    original_storage = service._storage
    service._storage = None
    try:
        cached_report = service.get_ceiling_analysis(test_date)
        assert cached_report is not None
        assert cached_report.title == report.title
        print(f"\n[Test Result] 캐시 히트 성공: {cached_report.title}")
    finally:
        service._storage = original_storage
    
    print(f"기간: {report.start_date} ~ {report.end_date}")
    print(f"항목 수: {len(report.items)}")
    print(f"샘플 항목: {report.items[0].name}")
