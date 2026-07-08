import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock
import pytest

from evenezer.application.services.news_service import NewsService
from evenezer.domain.news.models import NewsBatch, NewsItem
from evenezer.infrastructure.adapters.local.file_storage import LocalFileStorageAdapter
from evenezer.infrastructure.adapters.local.news_repo import LocalNewsRepository


@pytest.fixture
def setup_dirs(tmp_path):
    local_dir = tmp_path / "local"
    remote_dir = tmp_path / "remote"
    local_dir.mkdir()
    remote_dir.mkdir()
    return local_dir, remote_dir


@pytest.fixture
def news_integration_setup(setup_dirs):
    local_dir, remote_dir = setup_dirs
    local_repo = LocalNewsRepository(base_dir=local_dir)
    drive_adapter = LocalFileStorageAdapter(base_dir=remote_dir)

    # Scraper는 가짜 Mock 사용
    scraper = AsyncMock()

    service = NewsService(
        repository=local_repo,
        scraper=scraper,
        drive_adapter=drive_adapter,
        news_folder_id="news"
    )
    return service, local_repo, drive_adapter, local_dir, remote_dir


@pytest.mark.asyncio
async def test_integration_sync_merge_success(news_integration_setup):
    """로컬과 리모트에 각각 다른 기사가 있을 때, 동기화 후 양방향 병합되어 보존되어야 한다."""
    service, local_repo, drive_adapter, local_dir, remote_dir = news_integration_setup

    date_str = "2026-07-08"
    item_local = NewsItem(id="hash_local", title="로컬 뉴스", url="http://local.com", collected_at=datetime.now() - timedelta(minutes=10))
    item_remote = NewsItem(id="hash_remote", title="리모트 뉴스", url="http://remote.com", collected_at=datetime.now() - timedelta(minutes=5))

    # 1. 로컬 상태 설정
    batch_local = NewsBatch(date=date_str, items=[item_local], last_modified=datetime(2026, 7, 8, 10, 0))
    local_repo.save_batch(batch_local)
    local_repo.save_sync_metadata({f"news_{date_str}.json": "2026-07-08T10:00:00Z"})

    # 2. 리모트 상태 설정
    # Remote 폴더 내의 news 서브디렉토리에 저장해야 함 (NewsService 동기화 폴더 기준)
    remote_news_dir = remote_dir / "news"
    remote_news_dir.mkdir(exist_ok=True)

    batch_remote = NewsBatch(date=date_str, items=[item_remote], last_modified=datetime(2026, 7, 8, 11, 0))
    with open(remote_news_dir / f"news_{date_str}.json", "w", encoding="utf-8") as f:
        f.write(batch_remote.model_dump_json(indent=2))

    remote_metadata = {f"news_{date_str}.json": "2026-07-08T11:00:00Z"}
    with open(remote_news_dir / "news_metadata.json", "w", encoding="utf-8") as f:
        f.write(json.dumps(remote_metadata, indent=2))

    # 3. 동기화 실행
    await service.sync_from_drive()

    # 4. 검증: 양쪽 기사 모두 병합되었는지 확인
    updated_local_batch = local_repo.load_batch(date_str)
    assert updated_local_batch is not None
    item_ids = {it.id for it in updated_local_batch.items}
    assert item_ids == {"hash_local", "hash_remote"}

    # 리모트 파일도 병합되어 업로드 완료되었는지 검증
    remote_file_content = await drive_adapter.get_file(f"news_{date_str}.json", folder="news")
    assert remote_file_content is not None
    remote_batch = NewsBatch.model_validate(json.loads(remote_file_content.decode("utf-8")))
    assert len(remote_batch.items) == 2


@pytest.mark.asyncio
async def test_integration_delete_news_and_tombstone(news_integration_setup):
    """기사를 삭제하면 Tombstone에 기록되고, 동기화 후 리모트에서도 정상 삭제되어야 한다."""
    service, local_repo, drive_adapter, local_dir, remote_dir = news_integration_setup

    date_str = "2026-07-08"
    item1 = NewsItem(id="hash_to_keep", title="남길 뉴스", url="http://keep.com", collected_at=datetime.now())
    item2 = NewsItem(id="hash_to_del", title="지울 뉴스", url="http://delete.com", collected_at=datetime.now())

    # 1. 초기 로컬/리모트 동일 상태 설정
    batch = NewsBatch(date=date_str, items=[item1, item2], last_modified=datetime(2026, 7, 8, 12, 0))
    local_repo.save_batch(batch)
    local_repo.save_sync_metadata({f"news_{date_str}.json": "2026-07-08T12:00:00Z"})

    remote_news_dir = remote_dir / "news"
    remote_news_dir.mkdir(exist_ok=True)
    with open(remote_news_dir / f"news_{date_str}.json", "w", encoding="utf-8") as f:
        f.write(batch.model_dump_json(indent=2))
    with open(remote_news_dir / "news_metadata.json", "w", encoding="utf-8") as f:
        f.write(json.dumps({f"news_{date_str}.json": "2026-07-08T12:00:00Z"}, indent=2))

    # 2. 로컬에서 기사 2번 삭제 수행 (delete_news_item API 호출)
    success = await service.delete_news_item(ticker=None, url="http://delete.com")
    assert success is True

    # 3. 로컬 Tombstone 생성 검증
    metadata = local_repo.load_sync_metadata()
    assert "deleted_news" in metadata
    assert "hash_to_del" in metadata["deleted_news"]

    # 4. 동기화 실행 (리모트에도 기사 2번이 삭제되도록 전파되어야 함)
    await service.sync_from_drive()

    # 5. 검증
    # 로컬에 남길 뉴스만 있는지 확인
    updated_local_batch = local_repo.load_batch(date_str)
    assert len(updated_local_batch.items) == 1
    assert updated_local_batch.items[0].id == "hash_to_keep"

    # 리모트 파일에서도 지울 뉴스가 제거되었는지 확인
    remote_file_content = await drive_adapter.get_file(f"news_{date_str}.json", folder="news")
    remote_batch = NewsBatch.model_validate(json.loads(remote_file_content.decode("utf-8")))
    assert len(remote_batch.items) == 1
    assert remote_batch.items[0].id == "hash_to_keep"


@pytest.mark.asyncio
async def test_integration_empty_batch_file_deletion(news_integration_setup):
    """배치 내 모든 뉴스가 삭제되어 비어 있게 되면, 로컬 및 원격 파일이 완전히 삭제되어야 한다."""
    service, local_repo, drive_adapter, local_dir, remote_dir = news_integration_setup

    date_str = "2026-07-08"
    item = NewsItem(id="hash_only", title="유일한 뉴스", url="http://only.com", collected_at=datetime.now())

    # 1. 로컬/리모트 상태 설정
    batch = NewsBatch(date=date_str, items=[item], last_modified=datetime(2026, 7, 8, 12, 0))
    local_repo.save_batch(batch)
    local_repo.save_sync_metadata({f"news_{date_str}.json": "2026-07-08T12:00:00Z"})

    remote_news_dir = remote_dir / "news"
    remote_news_dir.mkdir(exist_ok=True)
    with open(remote_news_dir / f"news_{date_str}.json", "w", encoding="utf-8") as f:
        f.write(batch.model_dump_json(indent=2))
    with open(remote_news_dir / "news_metadata.json", "w", encoding="utf-8") as f:
        f.write(json.dumps({f"news_{date_str}.json": "2026-07-08T12:00:00Z"}, indent=2))

    # 2. 로컬에서 유일한 기사 삭제 (공백 배치 생성)
    success = await service.delete_news_item(ticker=None, url="http://only.com")
    assert success is True

    # 3. 로컬 파일 시스템에서 JSON 파일이 삭제되었는지 검증
    local_file_path = local_dir / f"news_{date_str}.json"
    assert not local_file_path.exists()

    # 4. 동기화 실행 (리모트 측 JSON 파일도 지워져야 함)
    await service.sync_from_drive()

    # 5. 리모트의 JSON 파일이 unlinked 되었는지 검증
    remote_file_exists = await drive_adapter.path_exists(f"news_{date_str}.json", folder="news")
    assert not remote_file_exists
