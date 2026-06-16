import argparse
import logging
import os
import sys

# 프로젝트 루트를 경로에 추가
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from evenezer.infrastructure.container import container

# 로깅 설정
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("BatchSyncScript")


def run_batch_sync(start_date: str, end_date: str = None):
    """시장 데이터 일괄 수집 실행"""
    market_service = container.market_data_service

    logger.info(f"=== 배치 수집 시작: {start_date} ~ {end_date or '오늘'} ===")
    market_service.sync_range_data(start_date, end_date)
    logger.info("=== 모든 배치 수집 작업이 완료되었습니다 ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="KRX 시장 데이터 일괄 동기화 스크립트")
    parser.add_argument("--start", type=str, help="시작 날짜 (YYYYMMDD)", required=True)
    parser.add_argument("--end", type=str, help="종료 날짜 (YYYYMMDD), 생략 시 오늘까지")

    args = parser.parse_args()

    # 입력 값 검증 (간단히)
    if len(args.start) != 8:
        print("에러: 날짜 형식은 YYYYMMDD 여야 합니다.")
        sys.exit(1)

    run_batch_sync(args.start, args.end)
