import json
import logging
import asyncio
from collections.abc import Callable
from datetime import datetime
from typing import Any

from evenezer.domain.ports import StockSplitRepositoryPort, StoragePort
from evenezer.domain.statistics.models import StockSplitManifest

logger = logging.getLogger(__name__)


class StockSplitSyncService:
    """구글 드라이브 주식 분할(액면분할) 데이터 동기화 서비스."""

    def __init__(
        self,
        repository: StockSplitRepositoryPort,
        drive_adapter: StoragePort | None,
        stock_split_folder_id: str | None,
    ) -> None:
        self._repository = repository
        self._drive_adapter = drive_adapter
        self._folder_id = stock_split_folder_id

    async def sync(self, progress_callback: Callable[[str, float], None] | None = None) -> bool:
        """구글 드라이브로부터 주식 분할 데이터를 로컬 저장소와 병렬로 안전하게 동기화합니다."""
        if not self._drive_adapter or not self._folder_id:
            msg = "Google Drive 어댑터 또는 주식분할 폴더 ID가 지정되지 않아 동기화를 생략합니다."
            logger.warning(msg)
            if progress_callback:
                progress_callback(msg, 0.0)
            return False

        if progress_callback:
            progress_callback("주식 분할 구글 동기화 시작...", 0.1)

        try:
            # 1. 드라이브 폴더 내 파일 목록 조회 (StoragePort 추상 메서드 사용)
            files = await self._drive_adapter.list_files_in_folder("", root_id=self._folder_id)
            
            # 매니페스트 파일 찾기
            manifest_file = next((f for f in files if "manifest" in f.get("name", "").lower()), None)
            if not manifest_file:
                logger.error("[StockSplitSync] 구글 드라이브에서 매니페스트 파일을 찾을 수 없습니다.")
                return False

            # 2. 매니페스트 다운로드 및 파싱
            logger.info(f"[StockSplitSync] 매니페스트 다운로드 시도: {manifest_file['name']}")
            manifest_data = await self._drive_adapter.get_file(manifest_file["name"], root_id=self._folder_id)
            if not manifest_data:
                logger.error("[StockSplitSync] 매니페스트 파일 다운로드 실패")
                return False

            remote_manifest = StockSplitManifest.model_validate(json.loads(manifest_data.decode("utf-8")))
            local_manifest = self._repository.load_manifest()

            # 3. 동기화 조건 체크
            need_sync = False
            if not local_manifest:
                need_sync = True
                logger.info("[StockSplitSync] 로컬 매니페스트가 없어 전체 동기화를 실행합니다.")
            else:
                # remote의 last_updated 가 더 최신인지 비교
                try:
                    remote_time = datetime.fromisoformat(remote_manifest.last_updated)
                    local_time = datetime.fromisoformat(local_manifest.last_updated)
                    if remote_time > local_time:
                        need_sync = True
                        logger.info(f"[StockSplitSync] 원격 데이터가 최신입니다 ({remote_manifest.last_updated} > {local_manifest.last_updated}). 동기화를 실행합니다.")
                except Exception:
                    need_sync = True  # 시간 비교 에러 시 안전하게 동기화 강행

            # 로컬 파일 존재 체크(로컬에 파일이 유실되었을 수 있으므로)
            for year in remote_manifest.supported_years:
                mtime = self._repository.get_file_mtime(f"액면분할({year}년).xlsx")
                if mtime is None:
                    need_sync = True
                    logger.info(f"[StockSplitSync] 로컬에 액면분할({year}년).xlsx 파일이 유실되어 동기화를 실행합니다.")

            if not need_sync:
                logger.info("[StockSplitSync] 로컬 데이터가 이미 최신 상태이므로 동기화를 생략합니다.")
                if progress_callback:
                    progress_callback("이미 최신 상태입니다.", 1.0)
                return True

            # 4. 파일 병렬 다운로드 집행
            if progress_callback:
                progress_callback("주식 분할 연도별 엑셀 파일 다운로드 중...", 0.4)

            # 세마포어 제한으로 스레드 충돌 및 과도한 커넥션 차단
            sem = asyncio.Semaphore(4)

            async def _download_and_save_excel(year: str, drive_file: dict):
                async with sem:
                    logger.info(f"[StockSplitSync] {year}년 엑셀 파일 다운로드 중: {drive_file['name']}")
                    data = await self._drive_adapter.get_file(drive_file["name"], root_id=self._folder_id)
                    if data:
                        # 로컬에는 규격화된 표준 이름인 '액면분할(202X년).xlsx'로 저장
                        self._repository.save_excel_file(f"액면분할({year}년).xlsx", data)
                        logger.info(f"[StockSplitSync] {year}년 엑셀 저장 완료: 액면분할({year}년).xlsx")
                        return True
                    else:
                        logger.error(f"[StockSplitSync] {year}년 엑셀 다운로드 실패: {drive_file['name']}")
                        return False

            tasks = []
            for year in remote_manifest.supported_years:
                # 드라이브 파일 중 이름에 해당 연도(예: 2024)가 있고 .xlsx로 끝나는 파일 찾기
                excel_file = next((f for f in files if year in f.get("name", "") and f.get("name", "").endswith(".xlsx")), None)
                if excel_file:
                    tasks.append(_download_and_save_excel(year, excel_file))
                else:
                    logger.warning(f"[StockSplitSync] {year}년에 해당하는 엑셀 파일을 드라이브 목록에서 찾지 못했습니다.")

            if tasks:
                results = await asyncio.gather(*tasks)
                if not all(results):
                    logger.warning("[StockSplitSync] 일부 파일 다운로드에 실패하였습니다.")
            
            # 5. 매니페스트 저장
            self._repository.save_manifest(remote_manifest)
            logger.info("[StockSplitSync] 로컬 매니페스트 갱신 및 저장 완료")

            if progress_callback:
                progress_callback("동기화 완료!", 1.0)
            return True

        except Exception as e:
            logger.exception(f"[StockSplitSync] 동기화 도중 치명적인 에러 발생: {e}")
            if progress_callback:
                progress_callback(f"동기화 실패: {e}", 1.0)
            return False
