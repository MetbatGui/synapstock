"""Google Drive 저장소 어댑터"""

import os
import io
import json
from typing import Optional, List, Any, Callable, Union
from pathlib import Path
import pandas as pd
import openpyxl
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from synapstock.domain.ports import StoragePort
import logging
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type, retry_if_result

logger = logging.getLogger(__name__)


class GoogleDriveAdapter(StoragePort):
    """Google Drive 저장소 Adapter.

    StoragePort를 구현하여 Google Drive에 데이터를 저장하고 로드합니다.
    OAuth 2.0 Token을 사용하여 인증합니다.
    """

    SCOPES = ['https://www.googleapis.com/auth/drive']

    def __init__(
        self, 
        token_file: str, 
        root_folder_name: str = "KRX_Auto_Crawling_Data", 
        root_folder_id: Optional[str] = None,
        client_secret_file: Optional[str] = None
    ):
        """GoogleDriveAdapter 초기화.

        Args:
            token_file (str): Token JSON 파일 경로.
            root_folder_name (str): 데이터를 저장할 최상위 폴더 이름.
            root_folder_id (Optional[str]): 데이터를 저장할 최상위 폴더 ID.
            client_secret_file (Optional[str]): Refresh Token 갱신을 위한 Client Secret 파일 경로.
        """
        self.token_file = token_file
        self.client_secret_file = client_secret_file
        
        if not self.token_file:
            raise ValueError("token_file must be provided.")
            
        if not os.path.exists(self.token_file):
             raise FileNotFoundError(f"Token file not found: {self.token_file}")

        self.drive_service = self._authenticate()
        
        if root_folder_id:
            self.root_folder_id = root_folder_id
        else:
            self.root_folder_id = self._get_or_create_folder(root_folder_name)

    def _authenticate(self):
        """Google Drive API 인증 (OAuth 2.0 Token)."""
        try:
            creds = Credentials.from_authorized_user_file(self.token_file, self.SCOPES)
            
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(self.token_file, 'w') as token:
                    token.write(creds.to_json())
                    
            return build('drive', 'v3', credentials=creds)
        except Exception as e:
            raise RuntimeError(f"Google Drive 인증 실패: {e}")

    @retry(wait=wait_exponential(multiplier=1, max=10), stop=stop_after_attempt(3))
    def _get_or_create_folder(self, folder_name: str, parent_id: str = 'root') -> str:
        """폴더를 찾거나 생성합니다."""
        query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and '{parent_id}' in parents and trashed = false"
        results = self.drive_service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get('files', [])

        if files:
            return files[0]['id']
        else:
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [parent_id]
            }
            file = self.drive_service.files().create(body=file_metadata, fields='id').execute()
            return file.get('id')

    @retry(wait=wait_exponential(multiplier=1, max=10), stop=stop_after_attempt(3))
    def _get_file_id(self, path: str) -> Optional[str]:
        """경로에 해당하는 파일/폴더의 ID를 찾습니다."""
        parts = path.strip("/").split("/")
        current_parent_id = self.root_folder_id
        
        for part in parts:
            query = f"name = '{part}' and '{current_parent_id}' in parents and trashed = false"
            results = self.drive_service.files().list(q=query, fields="files(id, mimeType)").execute()
            files = results.get('files', [])
            
            if not files:
                return None
            current_parent_id = files[0]['id']
            
        return current_parent_id

    def _ensure_path_directories(self, path: str) -> str:
        """파일 경로의 상위 디렉토리들을 생성하고 마지막 부모 폴더 ID를 반환합니다."""
        parts = path.strip("/").split("/")
        dir_parts = parts[:-1]
        
        current_parent_id = self.root_folder_id
        for part in dir_parts:
            current_parent_id = self._get_or_create_folder(part, current_parent_id)
            
        return current_parent_id

    def save_dataframe_excel(self, df: pd.DataFrame, path: str, **kwargs) -> bool:
        """DataFrame을 엑셀 파일로 Google Drive에 저장합니다.

        Args:
            df (pd.DataFrame): 저장할 데이터프레임.
            path (str): Google Drive 상의 대상 파일 경로.
            **kwargs: to_excel로 전달할 추가 인자.

        Returns:
            bool: 저장 성공 여부.
        """
        try:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, **kwargs)
            output.seek(0)
            self._upload_file(output, path, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            return True
        except Exception as e:
            logger.error(f"[GoogleDrive] Excel 업로드 실패 ({path}): {e}")
            return False

    def save_dataframe_csv(self, df: pd.DataFrame, path: str, **kwargs) -> bool:
        """DataFrame을 CSV 파일로 Google Drive에 저장합니다.

        Args:
            df (pd.DataFrame): 저장할 데이터프레임.
            path (str): Google Drive 상의 대상 파일 경로.
            **kwargs: to_csv로 전달할 추가 인자 (예: encoding='cp949').

        Returns:
            bool: 저장 성공 여부.
        """
        try:
            encoding = kwargs.pop('encoding', 'cp949')
            output_str = io.StringIO()
            df.to_csv(output_str, **kwargs)
            output_bytes = io.BytesIO(output_str.getvalue().encode(encoding))
            self._upload_file(output_bytes, path, 'text/csv')
            return True
        except Exception as e:
            logger.error(f"[GoogleDrive] CSV 업로드 실패 ({path}): {e}")
            return False

    def save_workbook(self, book: openpyxl.Workbook, path: str) -> bool:
        """OpenPyXL Workbook 객체를 Google Drive에 저장합니다.

        Args:
            book (openpyxl.Workbook): 저장할 엑셀 워크북 책 객체.
            path (str): Google Drive 상의 대상 파일 경로.

        Returns:
            bool: 저장 성공 여부.
        """
        try:
            output = io.BytesIO()
            book.save(output)
            output.seek(0)
            self._upload_file(output, path, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            return True
        except Exception as e:
            logger.error(f"[GoogleDrive] Workbook 업로드 실패 ({path}): {e}")
            return False

    @retry(wait=wait_exponential(multiplier=1, max=10), stop=stop_after_attempt(3))
    def _upload_file(self, data: io.BytesIO, path: str, mime_type: str):
        filename = os.path.basename(path)
        parent_id = self._ensure_path_directories(path)
        
        query = f"name = '{filename}' and '{parent_id}' in parents and trashed = false"
        results = self.drive_service.files().list(q=query, fields="files(id)").execute()
        files = results.get('files', [])

        media = MediaIoBaseUpload(data, mimetype=mime_type, resumable=True)

        if files:
            file_id = files[0]['id']
            self.drive_service.files().update(fileId=file_id, media_body=media).execute()
        else:
            file_metadata = {'name': filename, 'parents': [parent_id]}
            self.drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()

    def load_workbook(self, path: str) -> Optional[openpyxl.Workbook]:
        """Google Drive에서 엑셀 워크북을 로드합니다.

        Args:
            path (str): 로드할 Google Drive 경로.

        Returns:
            Optional[openpyxl.Workbook]: 로드된 워크북 객체 (실패 시 None).
        """
        try:
            file_id = self._get_file_id(path)
            if not file_id: return None
            request = self.drive_service.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
            fh.seek(0)
            return openpyxl.load_workbook(fh)
        except Exception as e:
            logger.error(f"[GoogleDrive] Workbook 로드 실패 ({path}): {e}")
            return None

    def path_exists(self, path: str) -> bool:
        return self._get_file_id(path) is not None

    def ensure_directory(self, path: str) -> bool:
        try:
            self._ensure_path_directories(path + "/dummy")
            return True
        except Exception:
            return False

    def load_dataframe(self, path: str, sheet_name: str = None, **kwargs) -> pd.DataFrame:
        """Google Drive에서 엑셀 파일을 읽어 DataFrame으로 반환합니다.

        Args:
            path (str): 로드할 Google Drive 리소스 경로.
            sheet_name (str, optional): 읽어들일 시트 이름.
            **kwargs: pd.read_excel에 전달할 추가 속성.

        Returns:
            pd.DataFrame: 데이터프레임. 못 찾거나 에러 시 빈 데이터프레임.
        """
        try:
            file_id = self._get_file_id(path)
            if not file_id: return pd.DataFrame()
            request = self.drive_service.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            fh.seek(0)
            target_sheet = 0 if sheet_name is None else sheet_name
            return pd.read_excel(fh, sheet_name=target_sheet, **kwargs)
        except Exception as e:
            logger.error(f"[GoogleDrive] DataFrame 로드 실패 ({path}): {e}")
            return pd.DataFrame()

    def get_file(self, path: str) -> Optional[bytes]:
        """Google Drive에서 바이너리 파일을 다운로드합니다.

        Args:
            path (str): 다운로드할 Google Drive 파일 경로.

        Returns:
            Optional[bytes]: 다운로드 받은 파일의 바이트 스트림. (실패 시 None)
        """
        try:
            file_id = self._get_file_id(path)
            if not file_id: return None
            request = self.drive_service.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            fh.seek(0)
            return fh.read()
        except Exception as e:
            logger.error(f"[GoogleDrive] 파일 로드 실패 ({path}): {e}")
            return None

    def put_file(self, path: str, data: bytes) -> bool:
        """바이너리 텍스트 데이터를 Google Drive에 직접 업로드합니다.

        Args:
            path (str): 저장할 대상 Google Drive 경로.
            data (bytes): 쓸 내용(바이트).

        Returns:
            bool: 성공 여부.
        """
        try:
            if path.endswith('.xlsx'):
                mime_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            elif path.endswith('.csv'):
                mime_type = 'text/csv'
            elif path.endswith('.pdf'):
                mime_type = 'application/pdf'
            else:
                mime_type = 'application/octet-stream'

            output = io.BytesIO(data)
            self._upload_file(output, path, mime_type)
            return True
        except Exception as e:
            logger.error(f"[GoogleDrive] 파일 업로드 실패 ({path}): {e}")
            return False

    @retry(wait=wait_exponential(multiplier=1, max=10), stop=stop_after_attempt(3))
    def list_files_in_folder(self, folder_path: str) -> List[dict]:
        """특정 폴더 내의 파일 목록을 가져옵니다.
        
        Returns:
            List[dict]: [{'id': '...', 'name': '...'}, ...]
        """
        folder_id = self._get_file_id(folder_path)
        if not folder_id:
            return []
            
        query = f"'{folder_id}' in parents and trashed = false"
        results = self.drive_service.files().list(q=query, fields="files(id, name)").execute()
        return results.get('files', [])

    def sync_pdf_reports(self, local_dir: str, drive_folder_path: str):
        """로컬 PDF 리포트를 Google Drive와 동기화합니다.
        
        기존에 드라이브에 있는 파일은 건너뛰고 없는 파일만 업로드합니다.
        """
        logger.info(f"[GoogleDrive] PDF 동기화 시작: Local={local_dir} -> Drive={drive_folder_path}")
        
        # 1. Google Drive 파일 목록 가져오기
        drive_files = self.list_files_in_folder(drive_folder_path)
        drive_file_names = {f['name'] for f in drive_files}
        
        # 2. 로컬 파일 목록 가져오기
        if not os.path.exists(local_dir):
            logger.warning(f"[GoogleDrive] 로컬 디렉토리가 존재하지 않습니다: {local_dir}")
            return
            
        local_files = [f for f in os.listdir(local_dir) if f.lower().endswith('.pdf')]
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
            
            with open(local_path, 'rb') as f:
                data = f.read()
                if self.put_file(drive_path, data):
                    logger.info(f"[GoogleDrive] 업로드 완료: {filename}")
                    count += 1
                else:
                    logger.error(f"[GoogleDrive] 업로드 실패: {filename}")
                    
        logger.info(f"[GoogleDrive] PDF 동기화 완료: {count}개 파일 업로드됨.")

    def download_file(self, filename: str, local_path: Union[str, Path]) -> bool:
        """Google Drive에서 단일 파일을 원자적으로(Atomic) 다운로드합니다.

        Args:
            filename (str): 다운로드할 Google Drive 상의 파일명.
            local_path (Union[str, Path]): 저장할 로컬 파일 경로.

        Returns:
            bool: 다운로드 성공 여부.

        Note:
            - 임시 파일(.tmp)에 먼저 쓰고 완료 후 이름을 변경하여 깨진 파일 생성을 방지합니다.
        """
        import tempfile
        import os
        from pathlib import Path

        try:
            results = self.drive_service.files().list(
                q=f"name = '{filename}' and '{self.root_folder_id}' in parents and trashed = false",
                fields="files(id, name)"
            ).execute()
            files = results.get('files', [])

            if not files:
                return False

            file_id = files[0]['id']
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
    def download_missing_reports(self, local_dir: str, report_list: List[dict], progress_callback: Optional[Callable[[str, float], Any]] = None):
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
        from pathlib import Path
        from concurrent.futures import ThreadPoolExecutor
        import threading
        import tempfile
        from googleapiclient.discovery import build
        
        if not os.path.exists(local_dir):
            os.makedirs(local_dir, exist_ok=True)
            
        local_files = {f.lower() for f in os.listdir(local_dir)}
        
        # 다운로드 대상 필터링
        to_download = [r for r in report_list if r.get('filename') and r.get('filename').lower() not in local_files]
        
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
            filename = report['filename']
            
            try:
                # 스레드 전용 서비스 생성 (캐시 문제 방지를 위해 로컬 변수로 관리)
                thread_service = build('drive', 'v3', credentials=creds, static_discovery=False)
                
                # 파일 ID 찾기 (서버 부하 분산 및 속도를 위해 직접 검색)
                query = f"name = '{filename}' and trashed = false"
                results = thread_service.files().list(q=query, fields="files(id)").execute()
                files = results.get('files', [])
                
                if not files:
                    with stats_lock:
                        failed_count += 1
                    return False

                file_id = files[0]['id']
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
                        if progress_callback and downloaded_count % 5 == 0:
                            progress_callback(f"다운로드 중... ({downloaded_count}/{to_download_count})", current_total_processed / total)
                    return True
                except Exception as e:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                    raise e
                    
            except Exception as e:
                with stats_lock:
                    failed_count += 1
                return False

        if progress_callback:
            progress_callback(f"병렬 다운로드 시작 (대상: {to_download_count}개, 스레드: 10)...", skipped_count / total)

        with ThreadPoolExecutor(max_workers=10) as executor:
            executor.map(download_worker, to_download)
                    
        if progress_callback:
            progress_callback(f"일괄 다운로드 완료. 신규: {downloaded_count}, 기존: {skipped_count}, 실패: {failed_count}", 1.0)
