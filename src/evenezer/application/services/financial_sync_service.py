from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from evenezer.domain.financials.repository import FinancialRepository
    from evenezer.domain.ports import StoragePort

from evenezer.domain.financials.models import FinancialMetric

logger = logging.getLogger(__name__)


class FinancialSyncService:
    """Google Drive 재무제표 데이터 동기화 서비스."""

    def __init__(
        self,
        drive_adapter: StoragePort | None,
        financial_statements_id: str | None,
        financial_dir: Path,
        financial_repo: FinancialRepository | None,
    ) -> None:
        """FinancialSyncService를 초기화합니다."""
        self._drive_adapter = drive_adapter
        self._financial_statements_id = financial_statements_id
        self._financial_dir = financial_dir
        self._financial_repo = financial_repo

    async def sync(self) -> bool:
        """Google Drive에 업로드된 최신 재무제표 엑셀 파일을 로컬에 동기화하고 캐시를 웜업합니다."""
        if not self._drive_adapter or not self._financial_statements_id:
            logger.info("[FinancialSync] 재무제표 구글 드라이브 ID가 없거나 어댑터가 활성화되지 않아 동기화를 건너뜁니다.")
            return False

        local_path = self._financial_dir / "재무제표.xlsx"
        logger.info(f"[FinancialSync] 재무제표 구글 드라이브 동기화 검사 시작 (ID: {self._financial_statements_id})")

        try:
            # 1. 구글 드라이브 ID 메타데이터 조회
            meta = await self._drive_adapter.get_file_metadata(self._financial_statements_id)
            if not meta:
                logger.error("[FinancialSync] 구글 드라이브에서 재무제표 메타데이터를 가져오지 못했습니다.")
                return False

            mime_type = meta.get("mimeType", "")
            target_file_id = self._financial_statements_id
            target_modified_time_str = meta.get("modifiedTime")

            # 2. 만약 폴더 ID인 경우, 폴더 내부에서 '재무제표' 이름을 포함한 최신 엑셀/스프레드시트 파일을 검색
            if mime_type == "application/vnd.google-apps.folder":
                logger.info("[FinancialSync] 제공된 ID가 폴더이므로 폴더 내부를 검색합니다.")

                def _find_file_in_folder():
                    try:
                        query = (
                            f"'{self._financial_statements_id}' in parents and trashed = false and "
                            f"(mimeType = 'application/vnd.google-apps.spreadsheet' or "
                            f"mimeType = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')"
                        )
                        results = (
                            self._drive_adapter.service.files()
                            .list(
                                q=query,
                                fields="files(id, name, modifiedTime, mimeType)",
                                orderBy="modifiedTime desc"
                            )
                            .execute()
                        )
                        return results.get("files", [])
                    except Exception as e:
                        logger.error(f"[FinancialSync] 폴더 내 파일 검색 실패: {e}")
                        return []

                files = await asyncio.to_thread(_find_file_in_folder)
                if not files:
                    logger.error("[FinancialSync] 폴더 내에서 재무제표 엑셀 또는 스프레드시트 파일을 찾지 못했습니다.")
                    return False

                selected_file = next(
                    (f for f in files if "재무제표" in f.get("name", "")),
                    files[0]
                )

                target_file_id = selected_file["id"]
                target_modified_time_str = selected_file.get("modifiedTime")
                logger.info(
                    f"[FinancialSync] 동기화 대상 파일 발견: {selected_file.get('name')} (ID: {target_file_id})"
                )

            if not target_modified_time_str:
                logger.error("[FinancialSync] 대상 파일의 modifiedTime 정보가 없습니다.")
                return False

            # Drive 시간 파싱 (UTC -> datetime -> timestamp)
            drive_dt = datetime.fromisoformat(target_modified_time_str.replace("Z", "+00:00"))
            drive_mtime = drive_dt.timestamp()

            # 3. 로컬 파일 시간 조회
            local_mtime = 0.0
            if local_path.exists():
                local_mtime = os.path.getmtime(local_path)

            # 4. 변경 날짜 대조 후 가져오기
            if not local_path.exists() or (drive_mtime - local_mtime) > 1.0:
                logger.info(
                    f"[FinancialSync] 구글 드라이브 재무제표 파일이 더 최신입니다. 다운로드를 시작합니다. "
                    f"(Drive: {drive_dt}, Local Mtime: {datetime.fromtimestamp(local_mtime) if local_mtime else '없음'})"
                )

                data = await self._drive_adapter.get_file_by_id(target_file_id)
                if data:
                    local_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(local_path, "wb") as f:
                        f.write(data)

                    os.utime(local_path, (drive_mtime, drive_mtime))
                    logger.info("[FinancialSync] 재무제표 파일 다운로드 및 시간 동기화 성공!")
                else:
                    logger.error("[FinancialSync] 구글 드라이브에서 재무제표 파일 다운로드 실패")
                    return False
            else:
                logger.info("[FinancialSync] 로컬 재무제표 파일이 최신 상태입니다. 동기화를 건너뜁니다.")

            # 5. 재무제표 데이터를 메모리에 사전 적재 (Eager 로드 웜업)
            if local_path.exists() and self._financial_repo:
                try:
                    logger.info("[FinancialSync] 재무제표 데이터를 메모리에 사전 적재(Warm-up)합니다...")
                    self._financial_repo.load_all(FinancialMetric.REVENUE)
                    self._financial_repo.load_all(FinancialMetric.OPERATING_PROFIT)
                    self._financial_repo.load_all(FinancialMetric.NET_INCOME)
                    logger.info("[FinancialSync] 재무제표 데이터 사전 적재 완료!")
                except Exception as e:
                    logger.error(f"[FinancialSync] 재무제표 데이터 사전 적재 중 오류 발생: {e}")

            return True

        except Exception as e:
            logger.exception(f"[FinancialSync] 재무제표 동기화 중 에러 발생: {e}")
            return False
