import logging
import time
from pathlib import Path

import pytest

from synapstock.infrastructure.container import Container

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@pytest.mark.asyncio

async def test_ranking_cache_integration():
    """랭킹 시스템 캐싱 및 데이터 무결성 통합 테스트."""
    # 1. 컨테이너 초기화
    container = Container()
    stats_service = container.statistics_service
    ranking_svc = stats_service.ranking_svc

    # 2. 캐시 매니페스트 경로 확인
    manifest_path = Path("data/statistics/cache_manifest.json")

    # 3. 1차 동기화 실행 (데이터 가져오기)
    logger.info("--- 1차 동기화 시작 (네트워크 다운로드 발생 가능) ---")
    start_time = time.time()
    # 최근 2026-04-22 데이터로 테스트
    res1 = await ranking_svc.sync_data("2026-04-22")
    duration1 = time.time() - start_time

    logger.info(f"1차 동기화 완료: {len(res1)}개 항목, 소요시간: {duration1:.2f}s")

    # 4. 캐시 파일 생성 확인
    assert manifest_path.exists(), "캐시 매니페스트 파일이 생성되어야 합니다."

    # 5. 2차 동기화 실행 (캐시 작동 확인)
    logger.info("\n--- 2차 동기화 시작 (캐시 적중 예상) ---")
    start_time = time.time()
    res2 = await ranking_svc.sync_data("2026-04-22")
    duration2 = time.time() - start_time

    logger.info(f"2차 동기화 완료: {len(res2)}개 항목, 소요시간: {duration2:.2f}s")

    # 6. 데이터 동일성 확인
    assert len(res1) == len(res2), "1차와 2차 동기화 결과 개수가 동일해야 합니다."

if __name__ == "__main__":
    test_ranking_cache_integration()
