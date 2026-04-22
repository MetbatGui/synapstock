"""Google Drive 저장소 어댑터"""

import io
import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from tenacity import retry, stop_after_attempt, wait_exponential

from synapstock.domain.ports import StoragePort

logger = logging.getLogger(__name__)


class GoogleDriveAdapter(StoragePort):
    """Google Drive 저장소 Adapter.

    StoragePort를 구현하여 Google Drive에 데이터를 저장하고 로드합니다.
    OAuth 2.0 Token을 사용하여 인증합니다.
    """

    SCOPES = ["https://www.googleapis.com/auth/drive"]

    def __init__(self, token_file: str, folders: dict[str, str] | None = None, client_secret_file: str | None = None):
        """GoogleDriveAdapter 초기화.

        Args:
            token_file (str): Token JSON 파일 경로.
            folders (dict[str, str]): {'name': 'id'} 형식의 폴더 매핑.
            client_secret_file (Optional[str]): Refresh Token 갱신을 위한 Client Secret 파일 경로.
        """
        self.token_file = token_file
        self.folders = folders or {}
        self.client_secret_file = client_secret_file

        if not self.token_file:
            raise ValueError("token_file must be provided.")

        if not os.path.exists(self.token_file):
            raise FileNotFoundError(f"Token file not found: {self.token_file}")

        self.drive_service = self._authenticate()

    def _get_root_id(self, folder: str | None = None) -> str:
        """키워드에 해당하는 폴더 ID를 반환합니다."""
        if not folder:
            if len(self.folders) == 1:
                return list(self.folders.values())[0]

            keys = ", ".join(self.folders.keys())
            raise ValueError(f"Multiple folders available ({keys}). Please specify 'folder' keyword.")

        if folder not in self.folders:
            keys = ", ".join(self.folders.keys())
            raise ValueError(f"Folder keyword '{folder}' not found. Available: {keys}")

        return self.folders[folder]

    def _authenticate(self):
        """Google Drive API 인증 (OAuth 2.0 Token)."""
        logger.info(f"[GoogleDrive] 인증 시도 (Token: {self.token_file})")
        try:
            creds = Credentials.from_authorized_user_file(self.token_file, self.SCOPES)

            if creds and creds.expired and creds.refresh_token:
                logger.info("[GoogleDrive] 토큰 만료됨. 갱신 시도 중...")
                creds.refresh(Request())
                with open(self.token_file, "w") as token:
                    token.write(creds.to_json())
                logger.info("[GoogleDrive] 토큰 갱신 완료.")

            service = build("drive", "v3", credentials=creds)
            logger.info("[GoogleDrive] API 서비스 객체 생성 성공.")
            return service
        except Exception as e:
            logger.error("[GoogleDrive] 인증 실패", exc_info=True)
            raise RuntimeError(f"Google Drive 인증 실패: {e}")

    @retry(wait=wait_exponential(multiplier=1, max=10), stop=stop_after_attempt(3))
    def _get_or_create_folder(self, folder_name: str, parent_id: str = "root") -> str:
        """폴더를 찾거나 생성합니다."""
        query = (
            f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' "
            f"and '{parent_id}' in parents and trashed = false"
        )
        results = self.drive_service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get("files", [])

        if files:
            return str(files[0]["id"])
        else:
            file_metadata = {
                "name": folder_name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_id],
            }
            file = self.drive_service.files().create(body=file_metadata, fields="id").execute()
            return cast(str, file.get("id", ""))

    @retry(wait=wait_exponential(multiplier=1, max=10), stop=stop_after_attempt(3))
    def _get_file_id(self, path: str, folder: str | None = None, root_id: str | None = None) -> str | None:
        """경로에 해당하는 파일/폴더의 ID를 찾습니다."""
        parts = path.strip("/").split("/")

        # 1. 명시적 root_id -> 2. folder 키워드 -> 3. Error
        target_root_id = root_id or self._get_root_id(folder)
        current_parent_id = target_root_id

        import unicodedata

        for part in parts:
            if not part:
                continue

            # 한글 유니코드 정규화(NFC/NFD) 문제 대응을 위해 하위 목록 전체 조회 후 비교
            results = (
                self.drive_service.files()
                .list(q=f"'{current_parent_id}' in parents and trashed = false", fields="files(id, name, mimeType)")
                .execute()
            )
            files = results.get("files", [])

            # 정확히 일치하거나 NFC 정규화 시 일치하는 항목 검색
            part_nfc = unicodedata.normalize("NFC", part)
            matched_file = None
            for f in files:
                name_nfc = unicodedata.normalize("NFC", f["name"])
                if name_nfc == part_nfc:
                    matched_file = f
                    break

            if not matched_file:
                return None
            current_parent_id = matched_file["id"]

        return current_parent_id

    def _ensure_path_directories(self, path: str, folder: str | None = None, root_id: str | None = None) -> str:
        """파일 경로의 상위 디렉토리들을 생성하고 마지막 부모 폴더 ID를 반환합니다."""
        parts = path.strip("/").split("/")
        dir_parts = parts[:-1]

        target_root_id = root_id or self._get_root_id(folder)
        current_parent_id = target_root_id
        for part in dir_parts:
            current_parent_id = self._get_or_create_folder(part, current_parent_id)

        return current_parent_id

    def get_file(self, path: str, folder: str | None = None, root_id: str | None = None, **kwargs) -> bytes | None:
        """Google Drive에서 바이너리 파일을 다운로드합니다."""
        logger.debug(f"[GoogleDrive] get_file 요청: {path} (folder={folder})")
        try:
            file_id = self._get_file_id(path, folder=folder, root_id=root_id)
            if not file_id:
                logger.warning(f"[GoogleDrive] 파일을 찾을 수 없음: {path}")
                return None

            request = self.drive_service.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            fh.seek(0)
            data = fh.read()
            logger.info(f"[GoogleDrive] 파일 로드 성공: {path} ({len(data)} bytes)")
            return data
        except Exception as e:
            logger.error(f"[GoogleDrive] 파일 로드 실패 ({path}): {e}", exc_info=True)
            return None

    def put_file(self, path: str, data: bytes, folder: str | None = None, root_id: str | None = None, **kwargs) -> bool:
        """바이너리 데이터를 Google Drive에 직접 업로드합니다."""
        try:
            if path.endswith(".xlsx"):
                mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            elif path.endswith(".csv"):
                mime_type = "text/csv"
            elif path.endswith(".pdf"):
                mime_type = "application/pdf"
            else:
                mime_type = "application/octet-stream"

            output = io.BytesIO(data)
            self._upload_file(output, path, mime_type, folder=folder, root_id=root_id)
            return True
        except Exception as e:
            logger.error(f"[GoogleDrive] 파일 업로드 실패 ({path}): {e}")
            return False

    @retry(wait=wait_exponential(multiplier=1, max=10), stop=stop_after_attempt(3))
    def _upload_file(
        self, data: io.BytesIO, path: str, mime_type: str, folder: str | None = None, root_id: str | None = None
    ):
        filename = os.path.basename(path)
        parent_id = self._ensure_path_directories(path, folder=folder, root_id=root_id)

        query = f"name = '{filename}' and '{parent_id}' in parents and trashed = false"
        results = self.drive_service.files().list(q=query, fields="files(id)").execute()
        files = results.get("files", [])

        media = MediaIoBaseUpload(data, mimetype=mime_type, resumable=True)

        if files:
            file_id = files[0]["id"]
            self.drive_service.files().update(fileId=file_id, media_body=media).execute()
        else:
            file_metadata = {"name": filename, "parents": [parent_id]}
            self.drive_service.files().create(body=file_metadata, media_body=media, fields="id").execute()

    def path_exists(self, path: str, folder: str | None = None, root_id: str | None = None, **kwargs) -> bool:
        return self._get_file_id(path, folder=folder, root_id=root_id) is not None

    def ensure_directory(self, path: str, folder: str | None = None, root_id: str | None = None, **kwargs) -> bool:
        try:
            self._ensure_path_directories(path + "/dummy", folder=folder, root_id=root_id)
            return True
        except Exception:
            return False

    def list_files_in_folder(self, folder_path: str, **kwargs) -> list[dict]:
        """특정 폴더 내의 파일 목록을 조회합니다 (재귀X, 단층)."""
        try:
            folder_id = self._get_file_id(folder_path, **kwargs)
            if not folder_id:
                return []

            query = f"'{folder_id}' in parents and trashed = false"
            results = (
                self.drive_service.files()
                .list(q=query, fields="files(id, name, mimeType, size, createdTime)", pageSize=1000)
                .execute()
            )

            files = results.get("files", [])
            logger.info(f"[GoogleDrive] 폴더 내 파일 조회 성공: {len(files)}개 발견")
            for f in files[:5]:
                logger.info(f"  - 파일: {f['name']} (ID: {f['id']})")
            return cast(list[dict], files)
        except Exception as e:
            logger.error(f"[GoogleDrive] 리스트 조회 실패 ({folder_path}): {e}")
            return []

    def sync_pdf_reports(self, local_dir: str, drive_folder_path: str):
        """로컬 PDF 리포트를 Google Drive와 동기화합니다.

        기존에 드라이브에 있는 파일은 건너뛰고 없는 파일만 업로드합니다.
        """
        logger.info(f"[GoogleDrive] PDF 동기화 시작: Local={local_dir} -> Drive={drive_folder_path}")

        # 1. Google Drive 파일 목록 가져오기
        drive_files = self.list_files_in_folder(drive_folder_path)
        drive_file_names = {f["name"] for f in drive_files}

        # 2. 로컬 파일 목록 가져오기
        if not os.path.exists(local_dir):
            logger.warning(f"[GoogleDrive] 로컬 디렉토리가 존재하지 않습니다: {local_dir}")
            return

        local_files = [f for f in os.listdir(local_dir) if f.lower().endswith(".pdf")]
        logger.info(f"[GoogleDrive] 로컬 파일 개수: {len(local_files)}")
        logger.info(f"[GoogleDrive] 드라이브 내 기존 파일 개수: {len(drive_file_names)}")

        # 3. 교차 검증 및 업로드
        count = 0
        for filename in local_files:
            if filename in drive_file_names:
                # print(f"[GoogleDrive] 건너뜀 (이미 존재): {filename}")
                continue

            local_path = os.path.join(local_dir, filename)
            drive_path = f"{drive_folder_path}/{filename}"

            with open(local_path, "rb") as f:
                data = f.read()
                if self.put_file(drive_path, data):
                    logger.info(f"[GoogleDrive] 업로드 완료: {filename}")
                    count += 1
                else:
                    logger.error(f"[GoogleDrive] 업로드 실패: {filename}")

        logger.info(f"[GoogleDrive] PDF 동기화 완료: {count}개 파일 업로드됨.")

    def download_file(
        self, filename: str, local_path: str | Path, folder: str | None = None, root_id: str | None = None
    ) -> bool:
        """Google Drive에서 단일 파일을 원자적으로(Atomic) 다운로드합니다.

        Args:
            filename (str): 다운로드할 Google Drive 상의 파일명.
            local_path (Union[str, Path]): 저장할 로컬 파일 경로.
            folder (Optional[str]): 등록된 폴더 키워드.
            root_id (Optional[str]): 대상 폴더 ID.

        Returns:
            bool: 다운로드 성공 여부.

        Note:
            - 임시 파일(.tmp)에 먼저 쓰고 완료 후 이름을 변경하여 깨진 파일 생성을 방지합니다.
        """
        import os
        import tempfile
        from pathlib import Path

        try:
            target_root_id = root_id or self._get_root_id(folder)
            results = (
                self.drive_service.files()
                .list(
                    q=f"name = '{filename}' and '{target_root_id}' in parents and trashed = false",
                    fields="files(id, name)",
                )
                .execute()
            )
            files = results.get("files", [])

            if not files:
                return False

            file_id = files[0]["id"]
            request = self.drive_service.files().get_media(fileId=file_id)

            local_path = Path(local_path)
            local_path.parent.mkdir(parents=True, exist_ok=True)

            temp_fd, temp_path = tempfile.mkstemp(dir=str(local_path.parent), suffix=".tmp")

            try:
                with os.fdopen(temp_fd, "wb") as f:
                    downloader = MediaIoBaseDownload(f, request)
                    done = False
                    while not done:
                        _, done = downloader.next_chunk()

                os.replace(temp_path, local_path)
                return True
            except Exception as e:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                logger.error(f"[GoogleDrive] 다운로드 중 오류: {e}")
                return False
        except Exception as e:
            logger.error(f"[GoogleDrive] 파일 조회 중 오류: {e}")
            return False

    def download_missing_reports(
        self, local_dir: str, report_list: list[dict], progress_callback: Callable[[str, float], Any] | None = None
    ):
        """로컬에 없는 리포트들을 Google Drive에서 병렬로 일괄 다운로드합니다.

        Args:
            local_dir (str): 리포트가 저장될 로컬 디렉토리 경로.
            report_list (List[dict]): 다운로드 대상 리포트 정보가 담긴 리스트. 각 항목은 'filename' 키를 포함해야 함.
            progress_callback (Optional[Callable[[str, float], Any]]): 진행 상태를 알리기 위한 콜백 함수.
                (메시지: str, 진행률: float) 형태의 인자를 받음.

        Note:
            - ThreadPoolExecutor를 사용하여 최대 10개의 파일을 병렬로 다운로드합니다.
            - 각 스레드는 독립적인 Drive API 서비스 객체를 생성하여 스레드 안전성을 보장합니다.
            - 원자적 쓰기(Atomic Write)를 위해 임시 파일(.tmp)에 먼저 저장 후 이동하는 방식을 사용합니다.
        """
        import os
        import tempfile
        import threading
        from concurrent.futures import ThreadPoolExecutor
        from pathlib import Path

        from googleapiclient.discovery import build

        if not os.path.exists(local_dir):
            os.makedirs(local_dir, exist_ok=True)

        local_files = {f.lower() for f in os.listdir(local_dir)}

        # 다운로드 대상 필터링
        to_download = []
        for r in report_list:
            fname = r.get("filename")
            if isinstance(fname, str) and fname.lower() not in local_files:
                to_download.append(r)

        total = len(report_list)
        to_download_count = len(to_download)

        if to_download_count == 0:
            if progress_callback:
                progress_callback(f"모든 리포트가 로컬에 존재합니다. (총 {total}개)", 1.0)
            return

        downloaded_count = 0
        failed_count = 0
        skipped_count = total - to_download_count

        stats_lock = threading.Lock()

        # 인증 정보를 사용하여 각 스레드에서 새로운 서비스 객체 생성 (Thread-safety)
        creds = Credentials.from_authorized_user_file(self.token_file, self.SCOPES)

        def download_worker(report):
            nonlocal downloaded_count, failed_count
            filename = report["filename"]

            try:
                # 스레드 전용 서비스 생성 (캐시 문제 방지를 위해 로컬 변수로 관리)
                thread_service = build("drive", "v3", credentials=creds, static_discovery=False)

                # 파일 ID 찾기 (서버 부하 분산 및 속도를 위해 직접 검색)
                query = f"name = '{filename}' and trashed = false"
                results = thread_service.files().list(q=query, fields="files(id)").execute()
                files = results.get("files", [])

                if not files:
                    with stats_lock:
                        failed_count += 1
                    return False

                file_id = files[0]["id"]
                request = thread_service.files().get_media(fileId=file_id)

                # 원자적 쓰기를 위해 임시 파일 사용
                local_path = Path(local_dir) / filename
                temp_fd, temp_path = tempfile.mkstemp(dir=local_dir, suffix=".tmp")

                try:
                    with os.fdopen(temp_fd, "wb") as f:
                        downloader = MediaIoBaseDownload(f, request)
                        done = False
                        while not done:
                            _, done = downloader.next_chunk()

                    # 다운로드 완료 후 이름 변경 (원자적 교체)
                    os.replace(temp_path, local_path)

                    with stats_lock:
                        downloaded_count += 1
                        current_total_processed = skipped_count + downloaded_count + failed_count
                        if progress_callback is not None and downloaded_count % 5 == 0:
                            progress_callback(
                                f"다운로드 중... ({downloaded_count}/{to_download_count})",
                                float(current_total_processed) / total,
                            )
                    return True
                except Exception as e:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                    raise e

            except Exception:
                with stats_lock:
                    failed_count += 1
                return False

        if progress_callback:
            progress_callback(f"병렬 다운로드 시작 (대상: {to_download_count}개, 스레드: 10)...", skipped_count / total)

        with ThreadPoolExecutor(max_workers=10) as executor:
            executor.map(download_worker, to_download)

        if progress_callback:
            progress_callback(
                f"일괄 다운로드 완료. 신규: {downloaded_count}, 기존: {skipped_count}, 실패: {failed_count}", 1.0
            )
