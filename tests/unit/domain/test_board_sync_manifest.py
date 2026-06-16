from datetime import datetime, UTC
from evenezer.domain.models import BoardSyncManifest, BoardManifestItem
from evenezer.domain.statistics.models import NewListing


def test_board_manifest_item_default():
    """BoardManifestItem의 기본값 및 속성이 올바르게 로드되는지 테스트합니다."""
    item = BoardManifestItem(name="테스트", last_modified=123.4)
    assert item.name == "테스트"
    assert item.last_modified == 123.4
    assert item.deleted is False


def test_update_board():
    """update_board 호출 시 보드 메타데이터가 갱신되고 타임스탬프가 생성되는지 검증합니다."""
    manifest = BoardSyncManifest()
    assert len(manifest.boards) == 0

    manifest.update_board("theme_IT", "IT섹터")
    assert "theme_IT" in manifest.boards
    assert manifest.boards["theme_IT"].name == "IT섹터"
    assert manifest.boards["theme_IT"].last_modified > 0
    assert manifest.boards["theme_IT"].deleted is False


def test_merge_with_boards_priority():
    """로컬과 원격의 보드 매니페스트 병합 시 타임스탬프 기반 최신성 보장 규칙을 검증합니다."""
    # 1. 로컬이 더 최신인 경우 (로컬 상태 보존)
    local = BoardSyncManifest(
        boards={
            "theme_IT": BoardManifestItem(name="IT_로컬", last_modified=200.0, deleted=False)
        }
    )
    remote = BoardSyncManifest(
        boards={
            "theme_IT": BoardManifestItem(name="IT_원격", last_modified=100.0, deleted=True)
        }
    )
    merged = local.merge_with(remote)
    assert merged.boards["theme_IT"].name == "IT_로컬"
    assert merged.boards["theme_IT"].deleted is False
    assert merged.boards["theme_IT"].last_modified == 200.0

    # 2. 원격이 더 최신인 경우 (원격 상태로 덮어쓰기)
    local2 = BoardSyncManifest(
        boards={
            "theme_IT": BoardManifestItem(name="IT_로컬", last_modified=100.0, deleted=False)
        }
    )
    remote2 = BoardSyncManifest(
        boards={
            "theme_IT": BoardManifestItem(name="IT_원격", last_modified=200.0, deleted=True)
        }
    )
    merged2 = local2.merge_with(remote2)
    assert merged2.boards["theme_IT"].name == "IT_원격"
    assert merged2.boards["theme_IT"].deleted is True
    assert merged2.boards["theme_IT"].last_modified == 200.0


def test_merge_with_listings_priority():
    """신규상장(IPO) 목록 병합 시 비즈니스 상태 우선순위(ASSIGNED > IGNORED > PENDING)에 부합하는지 검증합니다."""
    local = BoardSyncManifest(
        new_listings={
            "990001": NewListing(listing_date="2026-06-10", name="종목A", status="PENDING", updated_at="2026-06-10T12:00:00Z")
        }
    )
    remote = BoardSyncManifest(
        new_listings={
            "990001": NewListing(listing_date="2026-06-10", name="종목A", status="ASSIGNED", updated_at="2026-06-10T11:00:00Z")
        }
    )
    merged = local.merge_with(remote)
    # ASSIGNED 상태가 PENDING보다 우선하여 병합
    assert merged.new_listings["990001"].status == "ASSIGNED"
