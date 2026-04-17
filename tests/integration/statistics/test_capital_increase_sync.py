import os
import pytest
import logging
import re
from synapstock.infrastructure.container import Container
from synapstock.domain.statistics.models import PaidInCapitalIncrease

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_actual_capital_increase_sync_robust():
    """실제 구글 드라이브 데이터를 활용하여 동기화 및 파싱 전 과정을 정밀 검증합니다."""
    
    # 1. 환경 설정 및 컨테이너 초기화
    container = Container()
    stats_service = container.statistics_service
    config = container.config
    
    if not config.capital_increase_folder_id:
        pytest.skip("GOOGLE_DRIVE_CAPITAL_INCREASE_FOLDER_ID 환경 변수가 설정되지 않았습니다.")
    
    if not container.drive_adapter:
        pytest.skip("GoogleDriveAdapter가 초기화되지 않았습니다. (Token 파일 확인 필요)")

    logger.info(f"\n" + "="*50)
    logger.info(f"유상증자 정밀 통합 테스트 시작 (폴더 ID: {config.capital_increase_folder_id})")
    logger.info("="*50)

    # 2. 동기화 실행 (Listing -> Download -> Parsing -> Storage)
    # 개선된 헤더 자동 감지 로직이 포함된 파서가 동작합니다.
    items = stats_service.sync_capital_increase_data()
    
    # 3. 데이터 실존성 및 건수 검증
    assert items is not None, "❌ 동기화 결과가 None입니다."
    assert len(items) > 0, "❌ 파싱된 데이터가 0건입니다. 엑셀 구조나 헤더 감지 로직을 확인하세요."
    
    logger.info(f"✅ 총 {len(items)}건의 데이터를 성공적으로 파싱했습니다.")

    # 4. 연도별 분포 검증 (멀티 시트 파싱 확인)
    years = sorted(list(set(item.date[:4] for item in items if len(item.date) >= 4)))
    logger.info(f"✅ 포함된 연도 분포 ({len(years)}개 연도): {years}")
    assert len(years) >= 3, f"❌ 예상보다 적은 연도 데이터가 파싱되었습니다: {years}"

    # 5. 실사 데이터 정밀 매칭 (대한광통신 예시)
    dhk_items = [i for i in items if "대한광통신" in i.name]
    if dhk_items:
        logger.info(f"✅ '대한광통신' 데이터 {len(dhk_items)}건 발견.")
        sample = dhk_items[0]
        assert sample.new_shares > 0, "❌ 신주발행주식수가 0입니다."
        assert sample.date != "", "❌ 일자 데이터가 비어있습니다."
    else:
        logger.warning("⚠️ '대한광통신' 데이터를 찾지 못했습니다. 파일에 해당 종목이 있는지 확인 필요.")

    # 6. 수치 정합성 전수 조사 (Math Logic Integrity)
    error_count = 0
    for i, item in enumerate(items):
        expected_total = item.fund_facility + item.fund_operation + item.fund_acquisition + item.fund_etc
        if item.total_fund != expected_total:
            if error_count < 5: # 로그 폭주 방지
                logger.error(f"❌ 금액 불일치 발견 [{item.date} {item.name}]: Expected {expected_total}, Got {item.total_fund}")
            error_count += 1
    
    assert error_count == 0, f"❌ 총 {error_count}건의 자금 합계 불일치가 발견되었습니다."
    logger.info("✅ 모든 항목의 자금 조달 합계(total_fund) 정합성 확인 완료.")

    # 7. 데이터 품질 및 형식 검증
    date_pattern = re.compile(r"\d{4}-\d{2}-\d{2}")
    for item in items:
        # 유효한 날짜 형식이거나 비어있어야 함 (공시 데이터의 특성 반영)
        if item.date:
            assert date_pattern.match(item.date[:10]), f"❌ 잘못된 날짜 형식 발견: {item.date} ({item.name})"

    # 8. 티커 매핑 통계
    mapped_count = sum(1 for item in items if item.ticker is not None)
    mapping_rate = (mapped_count / len(items)) * 100
    logger.info(f"📊 티커 매핑 통계: {mapped_count}/{len(items)} ({mapping_rate:.1f}%)")
    
    # 9. 로컬 저장소 캐싱 확인
    repo_file = config.capital_increase_dir / "capital_increase_data.json"
    assert repo_file.exists(), "❌ 로컬 캐시 파일이 생성되지 않았습니다."
    
    logger.info("="*50)
    logger.info("✨ 유상증자 정밀 통합 테스트 최종 통과!")
    logger.info("="*50)

if __name__ == "__main__":
    test_actual_capital_increase_sync_robust()
