from datetime import datetime
from synapstock.domain.statistics.models import NewListing


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
