import os
import pytest
import logging
from synapstock.infrastructure.container import Container
from synapstock.domain.statistics.models import MarketType, SupplySubject

# 로깅 설정 (상세 로그 확인용)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_actual_gdrive_sync():
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
    synced_count = stats_service.sync_recent_data(limit=2)
    
    logger.info(f"Sync completed. Total synced dates: {synced_count}")
    
    # 5. 결과 검증
    # 로컬 저장소에 날짜 목록이 있는지 확인
    available_dates = stats_service._repository.list_available_dates(MarketType.KOSPI, SupplySubject.FOREIGN)
    logger.info(f"Available dates in local repository: {available_dates}")
    
    # 최소한 하나 이상의 날짜가 매칭되어야 함 (드라이브에 파일이 있다면)
    # assert synced_count >= 0  # 일단 실행 여부 확인
    
    # 6. 특정 날짜 데이터 로드 시도 (예: 가장 최근 날짜)
    if available_dates:
        latest_date = available_dates[0]
        ranking = stats_service.get_daily_ranking(latest_date, MarketType.KOSPI, SupplySubject.FOREIGN)
        assert ranking is not None
        assert len(ranking.items) > 0
        logger.info(f"Successfully loaded ranking for {latest_date}. Item count: {len(ranking.items)}")
    else:
        logger.warning("No dates found even after sync. Check folder access and file naming patterns on GDrive.")

if __name__ == "__main__":
    test_actual_gdrive_sync()
