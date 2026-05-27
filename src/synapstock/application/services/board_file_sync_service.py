import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from synapstock.domain.models import Board
from synapstock.domain.ports import BoardRepositoryPort
from synapstock.infrastructure.adapters.google.google_drive_adapter import GoogleDriveAdapter

logger = logging.getLogger(__name__)


class BoardFileSyncService:
    """통합 보드 파일 구글 드라이브 양방향 동기화 서비스.

    [도메인 철학]:
    - theme_*.json(Miro 연동형 보드)과 virtual_*.json(가상 보드)은 본질적으로 동일한 형식의 JSON 파일입니다.
    - 본 서비스는 두 가지 형식의 보드를 구별하지 않고, 단 하나의 구글 드라이브 테마 폴더(theme_folder_id) 내에서
      단일 상태 매니페스트(board_sync_manifest.json)를 기준으로 일원화하여 양방향 CRUD 동기화를 수행합니다.
    """

    def __init__(
        self,
        repository: BoardRepositoryPort,
        drive_adapter: GoogleDriveAdapter | None,
        theme_folder_id: str | None,
        manifest_path: Path = Path("data/board/board_sync_manifest.json"),
    ) -> None:
        """필요한 의존성으로 동기화 서비스를 초기화합니다."""
        self._repository = repository
        self._drive_adapter = drive_adapter
        self._theme_folder_id = theme_folder_id
        self._manifest_path = manifest_path
        self._manifest_path.parent.mkdir(parents=True, exist_ok=True)

    def load_local_manifest(self) -> dict[str, Any]:
        """로컬의 board_sync_manifest.json 상태 매니페스트를 로드합니다."""
        if not self._manifest_path.exists():
            return {"last_updated": "", "boards": {}}
        try:
            return json.loads(self._manifest_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"[BoardFileSync] 로컬 매니페스트 파싱 실패: {e}")
            return {"last_updated": "", "boards": {}}

    def save_local_manifest(self, manifest: dict[str, Any]) -> None:
        """로컬 상태 매니페스트를 물리 파일로 영속화합니다."""
        try:
            manifest["last_updated"] = datetime.now(UTC).isoformat()
            self._manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.error(f"[BoardFileSync] 로컬 매니페스트 저장 실패: {e}")

    def update_local_manifest(self, board_id: str, deleted: bool = False) -> None:
        """보드가 생성, 수정, 삭제(CRUD)되었을 때 매니페스트 상의 최종 수정 이력을 기록합니다."""
        # theme_* 혹은 virtual_* 보드 파일에 대해서만 이력을 갱신합니다.
        if not (board_id.startswith("virtual_") or board_id.startswith("theme_")):
            return

        manifest = self.load_local_manifest()

        # 표시 이름 정제
        if board_id.startswith("virtual_"):
            display_name = board_id.replace("virtual_", "")
        else:
            display_name = board_id.replace("theme_", "")

        manifest["boards"][board_id] = {
            "name": display_name,
            "last_modified": datetime.now(UTC).timestamp(),
            "deleted": deleted,
        }
        self.save_local_manifest(manifest)
        logger.info(f"[BoardFileSync] 로컬 매니페스트 갱신: {board_id} (deleted={deleted})")

    async def sync_with_drive(self, progress_callback: Callable[[str, float], None] | None = None) -> bool:
        """구글 드라이브와 로컬 저장소 간의 모든 보드 파일에 대해 양방향 동기화를 집행합니다."""
        if not self._drive_adapter or not self._theme_folder_id:
            msg = "Google Drive 어댑터 또는 테마 폴더 ID(theme_folder_id)가 지정되지 않아 동기화를 생략합니다."
            logger.warning(msg)
            if progress_callback:
                progress_callback(msg, 0.0)
            return False

        if progress_callback:
            progress_callback("구글 드라이브 상태 매니페스트 동기화 시작...", 0.1)

        manifest_filename = self._manifest_path.name

        # 1. 드라이브에서 원격 매니페스트 다운로드 시도
        remote_manifest: dict[str, Any] = {"last_updated": "", "boards": {}}
        try:
            remote_data = await self._drive_adapter.get_file(manifest_filename, root_id=self._theme_folder_id)
            if remote_data:
                remote_manifest = json.loads(remote_data.decode("utf-8"))
                logger.info("[BoardFileSync] 원격 상태 매니페스트 로드 성공.")
        except Exception as e:
            logger.error(f"[BoardFileSync] 원격 매니페스트 다운로드 실패: {e}")

        # 2. 로컬과 원격의 수정 시간(Timestamp)을 기준으로 상태 병합
        local_manifest = self.load_local_manifest()
        merged_boards = dict(remote_manifest.get("boards", {}))

        for b_id, l_info in local_manifest.get("boards", {}).items():
            if b_id not in merged_boards:
                merged_boards[b_id] = l_info
            else:
                r_info = merged_boards[b_id]
                l_modified = l_info.get("last_modified", 0.0)
                r_modified = r_info.get("last_modified", 0.0)
                # 더 최근에 편집된 쪽의 상태 정보를 최종 병합본으로 신뢰함
                if l_modified > r_modified:
                    merged_boards[b_id] = l_info

        merged_manifest = {
            "last_updated": datetime.now(UTC).isoformat(),
            "boards": merged_boards,
        }

        # 3. 병합된 최신 매니페스트를 기준으로 개별 보드 파일 동기화 집행
        total_items = len(merged_boards)
        if total_items == 0:
            if progress_callback:
                progress_callback("동기화할 보드가 디스크에 없습니다.", 1.0)
            self.save_local_manifest(merged_manifest)
            return True

        current_index = 0
        success_count = 0

        for b_id, info in merged_boards.items():
            current_index += 1
            progress_ratio = 0.1 + (float(current_index) / total_items) * 0.8
            board_filename = f"{b_id}.json"
            deleted = info.get("deleted", False)
            display_name = info.get("name", b_id)

            if deleted:
                # [CASE A] 드라이브상에서 지워진 보드 👉 로컬 파일 물리적 삭제
                try:
                    self._repository.delete(b_id)
                    logger.info(f"[BoardFileSync] 보드 물리적 삭제 완료: {board_filename}")
                except FileNotFoundError:
                    pass
                except Exception as e:
                    logger.error(f"[BoardFileSync] 보드 삭제 중 예외 ({b_id}): {e}")

                success_count += 1
                if progress_callback:
                    progress_callback(f"보드 삭제 반영: {display_name}", progress_ratio)
                continue

            l_info = local_manifest.get("boards", {}).get(b_id)
            r_info = remote_manifest.get("boards", {}).get(b_id)
            l_modified = l_info.get("last_modified", 0.0) if l_info else 0.0
            r_modified = r_info.get("last_modified", 0.0) if r_info else 0.0
            local_exists = b_id in self._repository.list_boards()

            try:
                if not local_exists and r_info:
                    # [CASE B] 로컬에는 없는데 드라이브에 존재함 👉 다운로드 후 로컬 생성
                    if progress_callback:
                        progress_callback(f"드라이브에서 파일 다운로드 중: {display_name}", progress_ratio)
                    data = await self._drive_adapter.get_file(board_filename, root_id=self._theme_folder_id)
                    if data:
                        board_json = json.loads(data.decode("utf-8"))
                        board = Board.model_validate(board_json)
                        board.id = b_id
                        self._repository.save(board)
                        success_count += 1
                        logger.info(f"[BoardFileSync] 신규 다운로드 성공: {board_filename}")

                elif local_exists and r_modified > l_modified:
                    # [CASE C] 원격 버전이 더 최신임 👉 다운로드 후 로컬 덮어쓰기
                    if progress_callback:
                        progress_callback(f"원격 최신 버전 다운로드 중: {display_name}", progress_ratio)
                    data = await self._drive_adapter.get_file(board_filename, root_id=self._theme_folder_id)
                    if data:
                        board_json = json.loads(data.decode("utf-8"))
                        board = Board.model_validate(board_json)
                        board.id = b_id
                        self._repository.save(board)
                        success_count += 1
                        logger.info(f"[BoardFileSync] 덮어쓰기 업데이트 성공: {board_filename}")

                elif local_exists and (not r_info or l_modified > r_modified):
                    # [CASE D] 로컬 버전이 더 최신이거나 로컬에만 있음 👉 구글 드라이브로 업로드
                    if progress_callback:
                        progress_callback(f"로컬 최신 버전 드라이브 업로드 중: {display_name}", progress_ratio)
                    board = self._repository.load(b_id)
                    board_bytes = board.model_dump_json(indent=2, exclude={"id"}, exclude_defaults=True).encode("utf-8")
                    up_success = await self._drive_adapter.put_file(
                        board_filename, board_bytes, root_id=self._theme_folder_id
                    )
                    if up_success:
                        success_count += 1
                        logger.info(f"[BoardFileSync] 파일 업로드 완료: {board_filename}")
                else:
                    success_count += 1
            except Exception as e:
                logger.error(f"[BoardFileSync] 보드 동기화 실패 ({b_id}): {e}", exc_info=True)

        # 4. 최종 완성된 병합 매니페스트 저장 및 구글 드라이브 업로드
        self.save_local_manifest(merged_manifest)
        try:
            manifest_bytes = json.dumps(merged_manifest, indent=2, ensure_ascii=False).encode("utf-8")
            await self._drive_adapter.put_file(manifest_filename, manifest_bytes, root_id=self._theme_folder_id)
            logger.info("[BoardFileSync] 원격 상태 매니페스트 최종 갱신 업로드 완료.")
        except Exception as e:
            logger.error(f"[BoardFileSync] 원격 매니페스트 최종 업로드 실패: {e}")

        if progress_callback:
            progress_callback(f"양방향 파일 동기화 완료! (성공: {success_count}/{total_items})", 1.0)
        return success_count == total_items
