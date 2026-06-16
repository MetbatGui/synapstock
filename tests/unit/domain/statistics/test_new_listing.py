from datetime import datetime
from evenezer.domain.statistics.models import NewListing


def test_merge_with_assigned_priority():
    """ASSIGNED 상태가 최우선으로 병합되는지 검증합니다."""
    # 1. PENDING vs ASSIGNED
    l_pending = NewListing(listing_date="2026-06-10", name="종목A", status="PENDING", updated_at="2026-06-10T12:00:00Z")
    r_assigned = NewListing(listing_date="2026-06-10", name="종목A", status="ASSIGNED", updated_at="2026-06-10T11:00:00Z")
    
    merged1 = l_pending.merge_with(r_assigned)
    assert merged1.status == "ASSIGNED"
    
    # 2. IGNORED vs ASSIGNED
    l_ignored = NewListing(listing_date="2026-06-10", name="종목A", status="IGNORED", updated_at="2026-06-10T12:00:00Z")
    
    merged2 = l_ignored.merge_with(r_assigned)
    assert merged2.status == "ASSIGNED"


def test_merge_with_ignored_priority():
    """IGNORED 상태가 PENDING보다 우선하여 병합되는지 검증합니다."""
    l_pending = NewListing(listing_date="2026-06-10", name="종목B", status="PENDING", updated_at="2026-06-10T11:00:00Z")
    r_ignored = NewListing(listing_date="2026-06-10", name="종목B", status="IGNORED", updated_at="2026-06-10T10:00:00Z")
    
    merged = l_pending.merge_with(r_ignored)
    assert merged.status == "IGNORED"


def test_merge_with_same_status_timestamp_priority():
    """상태가 동일한 경우 updated_at 타임스탬프가 더 최신인 쪽이 병합되는지 검증합니다."""
    # 둘 다 PENDING, 왼쪽이 더 최신
    l_pending_new = NewListing(listing_date="2026-06-10", name="종목C", status="PENDING", updated_at="2026-06-10T12:00:00Z")
    r_pending_old = NewListing(listing_date="2026-06-10", name="종목C", status="PENDING", updated_at="2026-06-10T11:00:00Z")
    
    merged1 = l_pending_new.merge_with(r_pending_old)
    assert merged1.updated_at == "2026-06-10T12:00:00Z"
    
    # 둘 다 ASSIGNED, 오른쪽이 더 최신
    l_assigned_old = NewListing(listing_date="2026-06-10", name="종목C", status="ASSIGNED", updated_at="2026-06-10T10:00:00Z")
    r_assigned_new = NewListing(listing_date="2026-06-10", name="종목C", status="ASSIGNED", updated_at="2026-06-10T11:00:00Z")
    
    merged2 = l_assigned_old.merge_with(r_assigned_new)
    assert merged2.updated_at == "2026-06-10T11:00:00Z"


def test_merge_with_same_status_timestamp_missing():
    """updated_at이 누락되었을 때의 안정적 기본 동작을 검증합니다."""
    l_no_time = NewListing(listing_date="2026-06-10", name="종목D", status="PENDING", updated_at=None)
    r_with_time = NewListing(listing_date="2026-06-10", name="종목D", status="PENDING", updated_at="2026-06-10T11:00:00Z")
    
    # 누락된 쪽(l_no_time = "") vs 존재하는 쪽(r_with_time = "2026-...")
    # "" >= "2026-..." 는 False이므로 r_with_time이 반환되어야 함
    merged = l_no_time.merge_with(r_with_time)
    assert merged.updated_at == "2026-06-10T11:00:00Z"


def test_new_listing_sync_domain_service():
    """NewListingSyncDomainService의 비즈니스 규칙 작동을 검증합니다."""
    from evenezer.domain.models import Board, Node, Stock
    from evenezer.domain.statistics.models import NewListing
    from evenezer.domain.statistics.domain_service import NewListingSyncDomainService

    # 1. 초기 상태 설정
    virtual_board = Board(id="virtual_신규상장주", name="신규상장주")
    root_node = virtual_board.root
    root_node.stocks.append(Stock(name="구형종목", ticker="111111"))
    root_node.stocks.append(Stock(name="대기종목", ticker="222222"))

    # 매니페스트 설정 (구형종목 2023년 상장, 대기종목 2025년 상장)
    new_listings_meta = {
        "111111": {"ticker": "111111", "name": "구형종목", "listing_date": "2023-12-12", "status": "PENDING"},
        "222222": {"ticker": "222222", "name": "대기종목", "listing_date": "2025-05-05", "status": "PENDING"},
    }

    # 수집된 신규 상장 목록
    listings = [
        # 신규 상장주 1 (PENDING)
        NewListing(ticker="333333", name="신규종목A", listing_date="2026-06-01", status="PENDING"),
        # 신규 상장주 2 (일반 테마보드 기등록 상태로 수집됨)
        NewListing(ticker="444443", name="기등록종목B", listing_date="2026-06-05", status="PENDING"),
    ]

    # 일반 테마보드 기등록 캐시 맵
    assigned_stocks_map = {
        "444443": ("theme_조선", ["조선", "기자재"])
    }

    now_str = "2026-06-12T12:00:00Z"

    # 2. 도메인 서비스 실행
    updated_board, updated_meta, changed = NewListingSyncDomainService.sync_listings_to_virtual_board(
        virtual_board=virtual_board,
        new_listings_meta=new_listings_meta,
        listings=listings,
        assigned_stocks_map=assigned_stocks_map,
        now_str=now_str
    )

    # 3. 비즈니스 규칙 검증
    assert changed is True

    # 3.1. 2024년 이전 구형 종목 청소 규칙 검증
    # 구형종목("111111")은 2023년 상장이므로 가상 보드에서 청소되었는지 확인
    assert not any(s.ticker == "111111" for s in updated_board.root.stocks)

    # 3.2. 기존 대기 종목(2025년 상장)은 그대로 보존되어야 함
    assert any(s.ticker == "222222" for s in updated_board.root.stocks)

    # 3.3. 신규 상장주 1 ("333333") 추가 규칙 검증
    # 신규 등록되어 PENDING 상태로 매니페스트에 적재되고 가상보드에 들어왔는지 확인
    assert updated_meta["333333"]["status"] == "PENDING"
    assert any(s.ticker == "333333" for s in updated_board.root.stocks)

    # 3.4. 일반 보드 기등록 종목 ("444443") 전이 규칙 검증
    # 상태가 ASSIGNED로 바뀌고, 가상 보드 대기 목록에는 추가되지 않아야 함
    assert updated_meta["444443"]["status"] == "ASSIGNED"
    assert updated_meta["444443"]["current_board"] == "theme_조선"
    assert updated_meta["444443"]["current_path"] == ["조선", "기자재"]
    assert not any(s.ticker == "444443" for s in updated_board.root.stocks)

