"""연도별 SQLite DB(SSOT)를 구독하는 범용 로컬 동기화 관리자.

여러 도메인(netbuy/ceiling/new_listing 등)이 "GDrive 폴더에 연도별 SQLite 파일이
있고, 구독자는 이를 다운로드해 로컬 캐시로 읽기만 한다"는 동일한 패턴을 쓴다.
weekly_change_db_sync.py에서 검증된 동기화 알고리즘(경로 존재 확인 -> 메타데이터
대조 -> 무결성 검증 -> 원자적 교체 -> TTL/force)을 도메인 무관하게 재사용하도록
일반화했다. docs/db_ssot_consumer_sync.md 참고.

TTL을 도입하면서 force 우회 경로도 반드시 같이 만든다 - weekly_change에서 TTL만
넣고 force_sync 전파를 빠뜨려 수동 새로고침이 무력화되는 회귀가 실제로 났었다
(docs/db_ssot_refactoring_guide.md 참고). ensure_db(force=True)로 항상 우회 가능.
"""

import hashlib
import json
import logging
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

_METADATA_TTL = timedelta(minutes=20)


class YearlyDbSync:
    """연도별 SQLite DB 파일 하나를 원격(Drive)과 동기화하고 로컬 경로를 보장한다."""

    def __init__(
        self,
        drive_adapter,
        data_root: str,
        folder_name: str,
        filename_for_year: Callable[[int], str],
        required_tables: set[str],
        subfolder: str = "",
    ):
        self.drive_adapter = drive_adapter
        self.folder_name = folder_name
        self.subfolder = subfolder
        self.filename_for_year = filename_for_year
        self.required_tables = required_tables
        self.root = Path(data_root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.root / "manifest.json"

    def _local_path(self, year: int) -> Path:
        return self.root / self.filename_for_year(year)

    def _load_manifest(self) -> dict:
        if not self.manifest_path.exists():
            return {}
        try:
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"[YearlyDbSync:{self.folder_name}] 매니페스트 로드 실패: {e}")
            return {}

    def _save_manifest(self, manifest: dict) -> None:
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _md5(path: Path) -> str:
        h = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()

    def _validate(self, path: Path) -> bool:
        """파일 존재, SQLite 무결성, 기대 테이블 존재 여부를 확인한다."""
        if not path.exists():
            return False
        try:
            conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
            try:
                cur = conn.cursor()
                if cur.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    return False
                tables = {r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                return self.required_tables.issubset(tables)
            finally:
                conn.close()
        except sqlite3.Error:
            return False

    def _write_manifest_entry(self, manifest: dict, key: str, remote_meta: dict, local_path: Path) -> None:
        now = datetime.now(UTC).isoformat()
        manifest[key] = {
            "drive_file_id": remote_meta.get("id"),
            "remote_modified_time": remote_meta.get("modifiedTime"),
            "remote_md5_checksum": remote_meta.get("md5Checksum"),
            "remote_size_bytes": remote_meta.get("size"),
            "local_md5": self._md5(local_path),
            "local_size_bytes": local_path.stat().st_size,
            "downloaded_at": now,
            "last_checked_at": now,
        }
        self._save_manifest(manifest)

    def _touch_last_checked(self, key: str) -> None:
        manifest = self._load_manifest()
        if key in manifest:
            manifest[key]["last_checked_at"] = datetime.now(UTC).isoformat()
            self._save_manifest(manifest)

    @staticmethod
    def _is_unchanged(entry: dict, remote_meta: dict) -> bool:
        return (
            entry.get("drive_file_id") == remote_meta.get("id")
            and entry.get("remote_md5_checksum") == remote_meta.get("md5Checksum")
            and entry.get("remote_modified_time") == remote_meta.get("modifiedTime")
        )

    @staticmethod
    def _within_ttl(entry: dict) -> bool:
        checked_at = entry.get("last_checked_at") or entry.get("downloaded_at")
        if not checked_at:
            return False
        try:
            checked = datetime.fromisoformat(checked_at)
        except ValueError:
            return False
        if checked.tzinfo is None:
            checked = checked.replace(tzinfo=UTC)
        return datetime.now(UTC) - checked < _METADATA_TTL

    async def _find_remote_file(self, year: int) -> dict | None:
        list_kwargs = {"folder": self.folder_name}
        if self.subfolder:
            root_files = await self.drive_adapter.list_files_in_folder("", folder=self.folder_name)
            sub_folder = next((f for f in (root_files or []) if f.get("name") == self.subfolder), None)
            if not sub_folder:
                return None
            list_kwargs = {"root_id": sub_folder["id"], "folder": self.folder_name}

        remote_files = await self.drive_adapter.list_files_in_folder("", **list_kwargs)
        filename = self.filename_for_year(year)
        return next((f for f in (remote_files or []) if f.get("name") == filename), None)

    async def _download_and_replace(self, file_id: str, key: str, remote_meta: dict, local_path: Path) -> bool:
        content = await self.drive_adapter.get_file_by_id(file_id)
        if not content:
            return False

        tmp_path = local_path.with_suffix(local_path.suffix + ".tmp")
        local_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path.write_bytes(content)

        if not self._validate(tmp_path):
            logger.error(f"[YearlyDbSync:{self.folder_name}] 다운로드한 DB 검증 실패, 기존 로컬 유지: {key}")
            tmp_path.unlink(missing_ok=True)
            return False

        tmp_path.replace(local_path)
        manifest = self._load_manifest()
        self._write_manifest_entry(manifest, key, remote_meta, local_path)
        return True

    def _try_reuse_local(self, key: str, local_path: Path, remote_meta: dict) -> bool:
        entry = self._load_manifest().get(key)
        if entry:
            unchanged = self._is_unchanged(entry, remote_meta)
            if unchanged:
                self._touch_last_checked(key)
            return unchanged

        if self._md5(local_path) == remote_meta.get("md5Checksum"):
            manifest = self._load_manifest()
            self._write_manifest_entry(manifest, key, remote_meta, local_path)
            return True
        return False

    async def ensure_db(self, year: int, force: bool = False) -> Path | None:
        """해당 연도의 DB를 최신 상태로 보장하고 로컬 경로를 반환한다.

        원격 확인 실패나 다운로드 실패 시에도, 이전에 검증된 로컬 DB가 있으면
        stale 상태로 재사용한다. 검증된 로컬 DB조차 없으면 None을 반환해
        동기화 실패를 데이터 없음처럼 위장하지 않는다 (db_ssot_guide.md §6.1).

        원격 메타데이터 확인은 짧은 TTL(20분) 안에서는 생략한다(§10.3).
        force=True면 TTL을 무시하고 항상 원격과 대조한다(수동 새로고침용).

        원격에 아예 없는 연도(예: 아직 발행 전인 미래 연도)도 "없음" 결과를 TTL로
        캐시한다 - 안 그러면 존재하지 않는 연도를 매 요청마다 Drive에 확인하게 된다.
        """
        if not self.drive_adapter:
            return None

        key = self.filename_for_year(year)
        local_path = self._local_path(year)
        local_valid = self._validate(local_path)

        if not force:
            entry = self._load_manifest().get(key)
            if local_valid and entry and self._within_ttl(entry):
                return local_path
            if not local_valid and entry and entry.get("not_found") and self._within_ttl(entry):
                return None

        remote = await self._find_remote_file(year)
        if not remote:
            if not local_valid:
                manifest = self._load_manifest()
                manifest[key] = {"not_found": True, "last_checked_at": datetime.now(UTC).isoformat()}
                self._save_manifest(manifest)
            return local_path if local_valid else None

        remote_meta = await self.drive_adapter.get_file_metadata(remote["id"])
        if not remote_meta:
            return local_path if local_valid else None

        if local_valid and self._try_reuse_local(key, local_path, remote_meta):
            return local_path

        downloaded = await self._download_and_replace(remote["id"], key, remote_meta, local_path)
        return local_path if downloaded or local_valid else None
