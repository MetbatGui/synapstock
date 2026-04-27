import logging

import pytest

from synapstock.domain.statistics.models import MarketType, SupplySubject
from synapstock.infrastructure.container import Container

# 로깅 설정 (상세 로그 확인용)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@pytest.mark.asyncio

async def test_actual_gdrive_sync():
    """실제 구글 드라이브와 연동하여 최근 데이터를 동기화하는 테스트."""
    # 1. 컨테이너 초기화 (실제 설정 및 어댑터 로드)
    container = Container()

    # 2. 서비스 가져오기
    stats_service = container.statistics_service

    # 3. 설정 확인 (sd_folder_id가 있어야 함)
    config = container.config
    if not config.sd_folder_id:
        pytest.skip("GOOGLE_DRIVE_SUPPLY_DEMAND_FOLDER_ID 환경 변수가 설정되지 않았습니다.")

    logger.info(f"Targeting SD Folder ID: {config.sd_folder_id}")

    # 4. 동기화 실행 (최근 2일치)
    # sync_recent_data 내부에 list_files_in_folder와 sync_from_storage 호출 로직이 있음
    synced_count = await stats_service.sync_recent_data(limit=2)

    logger.info(f"Sync completed. Total synced dates: {synced_count}")

    # 5. 결과 검증
    # 로컬 저장소에 날짜 목록이 있는지 확인
    available_dates = stats_service._repository.list_available_dates(MarketType.KOSPI, SupplySubject.FOREIGN)
    logger.info(f"Available dates in local repository: {available_dates}")

    # 최소한 하나 이상의 날짜가 매칭되어야 함 (드라이브에 파일이 있다면)
    # assert synced_count >= 0  # 일단 실행 여부 확인
    if available_dates:
        assert synced_count > 0, "데이터가 존재하면 첫 동기화 반환값도 > 0이어야 합니다."

    # 5.5 캐시 히트(이미 최신인 경우) 검증을 위한 2차 동기화 실행
    synced_count_2 = await stats_service.sync_recent_data(limit=2)
    logger.info(f"Second Sync completed (Cache hit test). Total synced dates: {synced_count_2}")
    if available_dates:
        assert synced_count_2 > 0, "캐시가 최신이어도 데이터를 올바르게 반환해야 합니다."

    # 6. 특정 날짜 데이터 로드 및 분석 검증 (연속 매수 일수 포함)
    target_date = "2026-04-24" # 가장 최근 날짜
    # get_daily_ranking은 원본 데이터를, get_analyzed_ranking은 분석(연속매수 등) 데이터를 반환함
    analysis = await stats_service.get_analyzed_ranking(target_date, MarketType.KOSPI, SupplySubject.FOREIGN)
    
    if analysis:
        assert len(analysis.items) > 0
        logger.info(f"Analysis results for {target_date}:")
        for item in analysis.items[:5]: # 상위 5개만 출력
            logger.info(f" - {item.name}: Rank {item.rank}, Consecutive: {item.consecutive_days} days")
        
        # 최소한 1일 이상은 나와야 함
        assert any(item.consecutive_days >= 1 for item in analysis.items)
    else:
        logger.warning(f"Analysis for {target_date} not found.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_actual_gdrive_sync())
