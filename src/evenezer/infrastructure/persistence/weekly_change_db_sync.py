"""weekly_change SQLite DB(krx-auto-crawling 발행)를 구독하는 로컬 동기화 관리자.

매니페스트는 순수 구독자(mindmap) 로컬 책임이며, 발행 측(krx-auto-crawling)은
이 상태를 알지도, 관여하지도 않는다. docs/db_ssot_consumer_sync.md 참고.
"""

import hashlib
import json
import logging
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

REQUIRED_TABLES = {"events", "items"}

# 원격 메타데이터 확인은 가볍지만 요청마다 실행할 필요는 없다 - 짧은 TTL이 지난
# 첫 요청에서만 재확인한다 (db_ssot_guide.md §10.3, docs/db_ssot_consumer_sync.md
# "동기화 알고리즘" §1). 페이지 하나가 열릴 때마다 연도x주기 조합별로 Drive API를
# 다회 호출하는 걸 막는 게 목적.
_METADATA_TTL = timedelta(minutes=20)


class WeeklyChangeDbSync:
    """weekly/monthly 등락률 SQLite DB를 원격(Drive)과 동기화하고 로컬 경로를 보장한다."""

    def __init__(self, drive_adapter, data_root: str = "data/statistics/weekly_change/db"):
        self.drive_adapter = drive_adapter
        self.root = Path(data_root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.root / "manifest.json"

    def _manifest_key(self, is_monthly: bool, year: int) -> str:
        return f"{'monthly' if is_monthly else 'weekly'}/{year}.db"

    def _local_path(self, is_monthly: bool, year: int) -> Path:
        sub = "monthly" if is_monthly else "weekly"
        return self.root / sub / f"{year}.db"

    def _load_manifest(self) -> dict:
        if not self.manifest_path.exists():
            return {}
        try:
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"[WeeklyChangeDbSync] 매니페스트 로드 실패: {e}")
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

    @staticmethod
    def _validate(path: Path) -> bool:
        """파일 존재, SQLite 무결성, 기대 테이블(events/items) 존재 여부를 확인한다."""
        if not path.exists():
            return False
        try:
            conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
            try:
                cur = conn.cursor()
                if cur.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    return False
                tables = {r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                return REQUIRED_TABLES.issubset(tables)
            finally:
                conn.close()
        except sqlite3.Error:
            return False

    @staticmethod
    def _max_last_trading_day(path: Path) -> str | None:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        try:
            row = conn.execute("SELECT MAX(last_trading_day) FROM events").fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    def _write_manifest_entry(self, manifest: dict, key: str, remote_meta: dict, local_path: Path) -> None:
        now = datetime.now(UTC).isoformat()
        manifest[key] = {
            "drive_file_id": remote_meta.get("id"),
            "remote_modified_time": remote_meta.get("modifiedTime"),
            "remote_md5_checksum": remote_meta.get("md5Checksum"),
            "remote_size_bytes": remote_meta.get("size"),
            "local_md5": self._md5(local_path),
            "local_size_bytes": local_path.stat().st_size,
            "data_max_date": self._max_last_trading_day(local_path),
            "downloaded_at": now,
            "last_checked_at": now,
        }
        self._save_manifest(manifest)

    def _touch_last_checked(self, key: str) -> None:
        """원격과 대조했는데 변경이 없었을 때 TTL 판단용 시각만 갱신한다."""
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
        """매니페스트 항목이 마지막으로 원격과 대조된 지 TTL 이내인지 확인한다."""
        checked_at = entry.get("last_checked_at") or entry.get("downloaded_at")
        if not checked_at:
            return False
        try:
            checked = datetime.fromisoformat(checked_at)
        except ValueError:
            return False
        if checked.tzinfo is None:
            # 과거(타임존 정보 없이 저장된) 매니페스트 항목 호환 - UTC로 가정한다.
            checked = checked.replace(tzinfo=UTC)
        return datetime.now(UTC) - checked < _METADATA_TTL

    async def _find_remote_file(self, year: int, is_monthly: bool) -> dict | None:
        subfolder = "db/monthly" if is_monthly else "db/weekly"
        remote_files = await self.drive_adapter.list_files_in_folder(subfolder, folder="weekly_change")
        return next((f for f in (remote_files or []) if f.get("name") == f"{year}.db"), None)

    async def _download_and_replace(self, file_id: str, key: str, remote_meta: dict, local_path: Path) -> bool:
        """원격 파일을 임시 경로로 받아 검증 후 원자적으로 교체한다. 성공 여부를 반환한다."""
        content = await self.drive_adapter.get_file_by_id(file_id)
        if not content:
            return False

        tmp_path = local_path.with_suffix(".db.tmp")
        local_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path.write_bytes(content)

        if not self._validate(tmp_path):
            logger.error(f"[WeeklyChangeDbSync] 다운로드한 DB 검증 실패, 기존 로컬 유지: {key}")
            tmp_path.unlink(missing_ok=True)
            return False

        tmp_path.replace(local_path)
        manifest = self._load_manifest()
        self._write_manifest_entry(manifest, key, remote_meta, local_path)
        return True

    def _try_reuse_local(self, key: str, local_path: Path, remote_meta: dict) -> bool:
        """검증된 로컬 DB가 원격과 이미 일치하면 True. 매니페스트가 없던 경우 새로 생성한다."""
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

    async def ensure_year_db(self, year: int, is_monthly: bool, force: bool = False) -> Path | None:
        """해당 연도의 weekly/monthly DB를 최신 상태로 보장하고 로컬 경로를 반환한다.

        원격 확인 실패나 다운로드 실패 시에도, 이전에 검증된 로컬 DB가 있으면
        stale 상태로 재사용한다. 검증된 로컬 DB조차 없으면 None을 반환해
        동기화 실패를 데이터 없음처럼 위장하지 않는다.

        원격 메타데이터 확인은 짧은 TTL(20분) 안에서는 생략한다 - 목록 조회
        화면 하나가 열릴 때마다 연도x주기 조합별로 Drive API를 다회 호출하는
        걸 막기 위함 (db_ssot_guide.md §10.3). force=True면 이 TTL 생략을
        건너뛰고 항상 원격과 대조한다 - 사용자가 명시적으로 동기화를 요청한
        경우(수동 새로고침)까지 TTL에 막히면 안 되기 때문
        (docs/db_ssot_consumer_sync.md "동기화 알고리즘" §1).
        """
        if not self.drive_adapter:
            return None

        key = self._manifest_key(is_monthly, year)
        local_path = self._local_path(is_monthly, year)
        local_valid = self._validate(local_path)

        if local_valid and not force:
            entry = self._load_manifest().get(key)
            if entry and self._within_ttl(entry):
                return local_path

        remote = await self._find_remote_file(year, is_monthly)
        if not remote:
            return local_path if local_valid else None

        remote_meta = await self.drive_adapter.get_file_metadata(remote["id"])
        if not remote_meta:
            return local_path if local_valid else None

        if local_valid and self._try_reuse_local(key, local_path, remote_meta):
            return local_path

        downloaded = await self._download_and_replace(remote["id"], key, remote_meta, local_path)
        return local_path if downloaded or local_valid else None
