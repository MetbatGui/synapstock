import json
import time
import uuid
from pathlib import Path
from typing import Any
from datetime import datetime

from synapstock.domain.ports import EventOutboxPort

class LocalFileEventOutboxAdapter(EventOutboxPort):
    """로컬 파일 시스템 기반의 EventOutboxPort 구현체."""

    def __init__(self, outbox_dir: Path | str) -> None:
        self.outbox_dir = Path(outbox_dir)
        self.archive_dir = self.outbox_dir / "archive"
        
        self.outbox_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

    def _serialize_event(self, event: Any) -> dict:
        """이벤트를 JSON 직렬화 가능한 딕셔너리로 변환합니다."""
        if hasattr(event, "to_dict"):
            return event.to_dict()
        elif hasattr(event, "model_dump"):
            return {
                "event_class": type(event).__name__,
                "data": event.model_dump()
            }
        elif hasattr(event, "__dict__"):
            return {
                "event_class": type(event).__name__,
                "data": event.__dict__
            }
        elif isinstance(event, dict):
            return event
        else:
            raise TypeError(f"직렬화할 수 없는 이벤트 타입입니다: {type(event)}")

    def save(self, event: Any) -> str:
        event_dict = self._serialize_event(event)
        
        # DomainEvent 인스턴스에 event_id가 있으면 이를 outbox_id로 사용하고, 
        # 없을 경우 하위 호환성을 위해 새로 생성합니다.
        outbox_id = getattr(event, "event_id", None) or event_dict.get("event_id")
        if not outbox_id:
            outbox_id = f"{int(time.time())}_{uuid.uuid4().hex}"
        
        payload = {
            "id": outbox_id,
            "event": event_dict,
            "status": "PENDING",
            "retry_count": 0,
            "last_error": None,
            "created_at": datetime.now().isoformat()
        }
        
        file_path = self.outbox_dir / f"{outbox_id}.json"
        file_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return outbox_id

    def load_pending(self) -> list[dict]:
        pending_list = []
        # outbox_dir 아래의 *.json 파일만 탐색 (하위 archive 폴더 내 파일은 제외)
        for p in self.outbox_dir.glob("*.json"):
            if p.is_file():
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                    if data.get("status") == "PENDING":
                        pending_list.append(data)
                except Exception:
                    # 손상된 파일 등의 경우 건너뜀
                    pass
        # 생성 시간순으로 정렬
        pending_list.sort(key=lambda x: x.get("created_at", ""))
        return pending_list

    def complete(self, outbox_id: str) -> None:
        file_path = self.outbox_dir / f"{outbox_id}.json"
        if file_path.exists():
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                data["status"] = "COMPLETED"
                data["completed_at"] = datetime.now().isoformat()
                
                # 아카이브 폴더로 이동
                archive_path = self.archive_dir / f"{outbox_id}.json"
                archive_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
                
                # 원본 삭제
                file_path.unlink()
            except Exception:
                pass

    def fail(self, outbox_id: str, error_msg: str) -> None:
        file_path = self.outbox_dir / f"{outbox_id}.json"
        if file_path.exists():
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                data["retry_count"] += 1
                data["last_error"] = error_msg
                data["updated_at"] = datetime.now().isoformat()
                
                file_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass
