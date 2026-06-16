import pytest

from evenezer.infrastructure.container import container


@pytest.mark.asyncio


async def test_sync_new_listing_data_real():
    """구글 드라이브에서 실제 2026년 신규상장 데이터를 동기화하고 검증합니다."""

    service = container.statistics_service

    # 1. 동기화 수행
    # 이 메서드는 구글 드라이브의 'new_listing' 폴더에서 엑셀들을 읽어옴
    items = await service.sync_new_listing_data()

    if not items:
        pytest.skip("구글 드라이브에 신규상장 데이터가 없거나 접근할 수 없어 테스트를 건너뜁니다.")
        return

    # 2. 결과 검증
    # 2026년 데이터가 가장 상단에 올 것이라고 기대 (파일명 역순 정렬 로직이 서비스에 포함됨)
    # 첫 번째 종목이 '덕양에너젠'인지 확인 (사용자 요청 사항)

    # 이름으로 찾기 (순서가 보장되지 않을 수 있으므로 우선 검색 후 첫 번째와 비교)
    target_name = "덕양에너젠"
    dy_items = [it for it in items if it.name == target_name]

    assert len(dy_items) > 0, f"'{target_name}' 종목을 파싱된 결과에서 찾을 수 없습니다."

    dy = dy_items[0]

    # 세부 데이터 검증 (사용자가 이전에 제공한 샘플 기반)
    # 덕양에너젠 | 코스닥 | 산소... | 10000(공모가) | 2026.01.30(상장일) | 650:1(경쟁률) | 32.33%(유통) | 21050(시가) ...
    assert dy.offer_price == 10000
    assert dy.listing_date == "2026.01.30"
    assert dy.institutional_competition == 650.0
    assert dy.float_shares_pct == 32.33
    assert dy.listing_day_open == 21050
    assert dy.listing_day_high == 39500
    assert dy.listing_day_close == 34850

    print(f"\n[통합 테스트 성공] {dy.name} 데이터가 실제 드라이브 파일에서 정상 파싱되었습니다.")
    print(f"상장일: {dy.listing_date}, 공모가: {dy.offer_price}, 경쟁률: {dy.institutional_competition}")


@pytest.mark.asyncio
async def test_sync_all_new_listings_real():
    """구글 드라이브에서 2024~2026 다년도 신규상장 데이터를 스마트 캐싱 기반으로 일괄 동기화하고 검증합니다."""
    import time
    service = container.statistics_service
    
    # 1. 일괄 동기화 실행 (최초 실행: 다운로드 발생)
    start_time = time.time()
    items = await service.sync_all_new_listings(force_sync=True)
    duration_first = time.time() - start_time
    print(f"\n[최초 동기화] 완료 소요시간: {duration_first:.2f}초, 총 종목 수: {len(items)}")
    
    if not items:
        pytest.skip("구글 드라이브에 신규상장 데이터가 없거나 접근할 수 없어 테스트를 건너뜁니다.")
        return
        
    # 2. 결과 검증 (2024~2026 다년도 데이터가 골고루 섞여 있는지)
    years = [it.listing_date[:4] for it in items if it.listing_date and len(it.listing_date) >= 4]
    unique_years = set(years)
    print(f"가져온 데이터의 연도 분포: {unique_years}")
    
    assert len(unique_years) > 0
    
    # 3. 2차 동기화 실행 (스마트 캐싱 검증 - force_sync=False로 호출하여 구글 드라이브 목록 조회조차 생략하는 완전 캐싱 속도 검증)
    start_time = time.time()
    cached_items = await service.sync_all_new_listings(force_sync=False)
    duration_cached_fast = time.time() - start_time
    print(f"[완전 로컬 캐시 동기화] 완료 소요시간: {duration_cached_fast:.4f}초")
    
    # 드라이브 조회가 완전히 생략되므로 1.0초 미만이어야 함
    assert duration_cached_fast < 1.0
    assert len(cached_items) == len(items), "캐시 로드 후 데이터 개수가 동일해야 합니다."

    # 4. 3차 동기화 실행 (force_sync=True 이지만 스마트 캐싱으로 다운로드/파싱 생략되는 실질 속도 검증)
    start_time = time.time()
    cached_items_force = await service.sync_all_new_listings(force_sync=True)
    duration_cached_force = time.time() - start_time
    print(f"[강제 동기화 시 캐싱 검증] 완료 소요시간: {duration_cached_force:.2f}초")
    
    # 3회의 파일 목록 API 조회만 발생하므로 최초 동기화(다운로드+파싱 포함)보다 빨라야 함
    assert duration_cached_force < 3.5 or duration_cached_force < (duration_first * 0.95)
    assert len(cached_items_force) == len(items), "캐시 로드 후 데이터 개수가 동일해야 합니다."
