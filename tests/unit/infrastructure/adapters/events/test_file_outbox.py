import pytest
import json
from pathlib import Path
from synapstock.domain.ports import EventOutboxPort
from synapstock.infrastructure.adapters.events.file_outbox import LocalFileEventOutboxAdapter

class DummyEvent:
    def __init__(self, value: str):
        self.value = value

@pytest.fixture
def temp_outbox_dir(tmp_path):
    outbox_dir = tmp_path / "outbox"
    outbox_dir.mkdir(parents=True, exist_ok=True)
    return outbox_dir

@pytest.mark.unit
def test_outbox_interface(temp_outbox_dir):
    """LocalFileEventOutboxAdapter가 EventOutboxPort 인스턴스인지 검증."""
    adapter = LocalFileEventOutboxAdapter(temp_outbox_dir)
    assert isinstance(adapter, EventOutboxPort)

@pytest.mark.unit
def test_save_and_load_pending(temp_outbox_dir):
    """이벤트 저장 후 PENDING 목록 조회가 정상적인지 검증."""
    adapter = LocalFileEventOutboxAdapter(temp_outbox_dir)
    
    event_data = {"event_type": "DummyEvent", "data": {"value": "hello_outbox"}}
    
    outbox_id = adapter.save(event_data)
    assert outbox_id is not None
    assert (temp_outbox_dir / f"{outbox_id}.json").exists()
    
    # PENDING 목록 조회
    pending = adapter.load_pending()
    assert len(pending) == 1
    assert pending[0]["id"] == outbox_id
    assert pending[0]["event"]["data"]["value"] == "hello_outbox"
    assert pending[0]["status"] == "PENDING"
    assert pending[0]["retry_count"] == 0

@pytest.mark.unit
def test_complete_moves_to_archive(temp_outbox_dir):
    """완료 처리 시 이벤트 파일이 archive 폴더로 성공적으로 이동하는지 검증."""
    adapter = LocalFileEventOutboxAdapter(temp_outbox_dir)
    event_data = {"event_type": "DummyEvent", "data": {"value": "complete_test"}}
    
    outbox_id = adapter.save(event_data)
    adapter.complete(outbox_id)
    
    # 원래 PENDING 파일은 지워지고
    assert not (temp_outbox_dir / f"{outbox_id}.json").exists()
    # 아카이브 폴더에 파일이 이동해 있어야 함
    archive_file = temp_outbox_dir / "archive" / f"{outbox_id}.json"
    assert archive_file.exists()
    
    # 파일 내의 status가 COMPLETED로 바뀌었는지 확인
    data = json.loads(archive_file.read_text(encoding="utf-8"))
    assert data["status"] == "COMPLETED"
    
    # PENDING 조회 시 비어있어야 함
    assert len(adapter.load_pending()) == 0

@pytest.mark.unit
def test_fail_updates_retry_info(temp_outbox_dir):
    """실패 처리 시 재시도 횟수 및 에러 로그가 파일에 갱신되는지 검증."""
    adapter = LocalFileEventOutboxAdapter(temp_outbox_dir)
    event_data = {"event_type": "DummyEvent", "data": {"value": "fail_test"}}
    
    outbox_id = adapter.save(event_data)
    
    # 1차 실패
    adapter.fail(outbox_id, "Connection Timeout")
    pending = adapter.load_pending()
    assert len(pending) == 1
    assert pending[0]["status"] == "PENDING"
    assert pending[0]["retry_count"] == 1
    assert pending[0]["last_error"] == "Connection Timeout"
    
    # 2차 실패
    adapter.fail(outbox_id, "Rate Limit Exceeded")
    pending = adapter.load_pending()
    assert pending[0]["retry_count"] == 2
    assert pending[0]["last_error"] == "Rate Limit Exceeded"
