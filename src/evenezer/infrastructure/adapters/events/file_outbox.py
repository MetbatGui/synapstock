import json
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from evenezer.domain.ports import EventOutboxPort


class LocalFileEventOutboxAdapter(EventOutboxPort):
    """로컬 파일 시스템 기반의 EventOutboxPort 구현체. 스레드 락킹과 데드레터 큐를 지원합니다."""

    def __init__(self, outbox_dir: Path | str) -> None:
        """LocalFileEventOutboxAdapter를 초기화합니다.

        Args:
            outbox_dir: 아웃박스 파일들이 관리될 기본 디렉토리 경로.
        """
        self.outbox_dir = Path(outbox_dir)
        self.archive_dir = self.outbox_dir / "archive"
        self.failed_dir = self.outbox_dir / "failed"

        self.outbox_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self.failed_dir.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()

    def _serialize_event(self, event: Any) -> dict:
        """이벤트를 JSON 직렬화 가능한 딕셔너리로 변환합니다.

        Args:
            event: 직렬화 대상 이벤트 인스턴스.

        Returns:
            직렬화된 이벤트 데이터 딕셔너리.

        Raises:
            TypeError: 지원하지 않는 형식의 객체인 경우.
        """
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
        """이벤트를 PENDING 상태의 JSON 파일로 아웃박스 디렉토리에 스레드-안전하게 저장합니다.

        Args:
            event: 저장할 도메인 이벤트 인스턴스.

        Returns:
            저장된 아웃박스 파일의 고유 식별자(ID) 문자열.
        """
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
        with self._lock:
            file_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return outbox_id

    def load_pending(self) -> list[dict]:
        """아웃박스 디렉토리에서 PENDING 상태인 대기 중인 이벤트 목록을 스레드-안전하게 조회합니다.

        Returns:
            생성일자 기준 시간 순서대로 정렬된 대기 이벤트 딕셔너리 리스트.
        """
        pending_list = []
        with self._lock:
            # outbox_dir 아래의 *.json 파일만 탐색 (하위 archive/failed 폴더 내 파일은 제외)
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
        """완료된 이벤트를 COMPLETED 상태로 아카이브 디렉토리에 백업하고 원본 파일을 제거합니다.

        Args:
            outbox_id: 완료 처리할 아웃박스 파일 고유 식별자.
        """
        file_path = self.outbox_dir / f"{outbox_id}.json"
        with self._lock:
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
        """이벤트 처리 실패 내역(재시도 카운트 및 마지막 예외 메시지)을 파일에 스레드-안전하게 반영합니다.

        Args:
            outbox_id: 실패를 기록할 아웃박스 파일 고유 식별자.
            error_msg: 실패 원인 에러 메시지.
        """
        file_path = self.outbox_dir / f"{outbox_id}.json"
        with self._lock:
            if file_path.exists():
                try:
                    data = json.loads(file_path.read_text(encoding="utf-8"))
                    data["retry_count"] += 1
                    data["last_error"] = error_msg
                    data["updated_at"] = datetime.now().isoformat()

                    file_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
                except Exception:
                    pass

    def fail_permanent(self, outbox_id: str, error_msg: str) -> None:
        """이벤트를 영구 실패 상태로 failed 디렉토리에 격리하고 원본 아웃박스 파일을 삭제합니다.

        Args:
            outbox_id: 영구 실패(Dead Letter) 처리할 아웃박스 파일 고유 식별자.
            error_msg: 최종 처리 실패 상세 에러 텍스트.
        """
        file_path = self.outbox_dir / f"{outbox_id}.json"
        with self._lock:
            if file_path.exists():
                try:
                    data = json.loads(file_path.read_text(encoding="utf-8"))
                    data["status"] = "FAILED_PERMANENT"
                    data["last_error"] = error_msg
                    data["failed_at"] = datetime.now().isoformat()

                    # 실패(failed) 폴더로 이동하여 격리
                    failed_path = self.failed_dir / f"{outbox_id}.json"
                    failed_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

                    # 원본 삭제
                    file_path.unlink()
                except Exception:
                    pass
