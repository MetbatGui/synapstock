import pytest
from unittest.mock import MagicMock, patch, ANY
import os
import io
from pathlib import Path
import threading

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

from evenezer.infrastructure.adapters.google.google_drive_adapter import GoogleDriveAdapter


# -----------------------------------------------------------------------------
# Mock Helpers for Google Drive API Chaining
# -----------------------------------------------------------------------------

class MockExecutable:
    def __init__(self, return_value=None, side_effect=None):
        self.execute = MagicMock(return_value=return_value, side_effect=side_effect)


class MockFilesResource:
    def __init__(self):
        self._list_res = MockExecutable(return_value={"files": []})
        self._create_res = MockExecutable(return_value={"id": "new_created_id"})
        self._update_res = MockExecutable(return_value={"id": "updated_id"})
        self._get_res = MockExecutable(return_value={})
        self._get_media_res = MagicMock()
        self._export_media_res = MagicMock()
        self._delete_res = MockExecutable(return_value={})

        self._list_mock = MagicMock()
        self._create_mock = MagicMock()
        self._update_mock = MagicMock()
        self._get_mock = MagicMock()
        self._get_media_mock = MagicMock()
        self._export_media_mock = MagicMock()
        self._delete_mock = MagicMock()

    def list(self, *args, **kwargs):
        self._list_mock(*args, **kwargs)
        return self._list_res

    def create(self, *args, **kwargs):
        self._create_mock(*args, **kwargs)
        return self._create_res

    def update(self, *args, **kwargs):
        self._update_mock(*args, **kwargs)
        return self._update_res

    def get(self, *args, **kwargs):
        self._get_mock(*args, **kwargs)
        return self._get_res

    def get_media(self, *args, **kwargs):
        self._get_media_mock(*args, **kwargs)
        return self._get_media_res

    def export_media(self, *args, **kwargs):
        self._export_media_mock(*args, **kwargs)
        return self._export_media_res

    def delete(self, *args, **kwargs):
        self._delete_mock(*args, **kwargs)
        return self._delete_res


class MockDriveService:
    def __init__(self):
        self._files = MockFilesResource()

    def files(self):
        return self._files


class MockMediaIoBaseDownload:
    """MediaIoBaseDownload 객체 생성 시점에 스트림에 즉시 모의 데이터를 기록하는 테스트 헬퍼 클래스입니다."""
    def __init__(self, fd, request, *args, **kwargs):
        self.fd = fd
        self.fd.write(b"mocked_data_bytes")

    def next_chunk(self):
        return None, True


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def temp_token_file(tmp_path):
    """실제 존재해야 하는 token_file을 모의로 생성합니다. Credentials에서 요구하는 필드를 포함합니다."""
    token_path = tmp_path / "token.json"
    token_path.write_text('{"client_id": "mock_id", "client_secret": "mock_secret", "refresh_token": "mock_refresh"}')
    return str(token_path)


@pytest.fixture
def mock_drive_service():
    """Google Drive API 서비스의 모의 객체를 제공합니다."""
    return MockDriveService()


@pytest.fixture(autouse=True)
def global_google_mocks(mock_drive_service):
    """모든 비동기/동적 스레드(로컬 임포트 포함)에서 구글 API 요청이 가로채지도록 Credentials와 build를 전역 패치합니다.
    'Patch where it is used' 규칙에 따라 모듈 전역 바인딩 네임스페이스와 라이브러리 네임스페이스 양쪽 모두를 패치합니다.
    """
    mock_creds = MagicMock()
    mock_creds.expired = False
    mock_creds.universe_domain = "googleapis.com"
    mock_creds.create_scoped.return_value.authorize.return_value.credentials.universe_domain = "googleapis.com"
    
    with patch("google.oauth2.credentials.Credentials.from_authorized_user_file", return_value=mock_creds), \
         patch("evenezer.infrastructure.adapters.google.google_drive_adapter.build", return_value=mock_drive_service) as mock_build1, \
         patch("googleapiclient.discovery.build", return_value=mock_drive_service) as mock_build2, \
         patch("evenezer.infrastructure.adapters.google.google_drive_adapter.MediaIoBaseDownload", new=MockMediaIoBaseDownload), \
         patch("googleapiclient.http.MediaIoBaseDownload", new=MockMediaIoBaseDownload):
        yield mock_build1


# -----------------------------------------------------------------------------
# Test GoogleDriveAdapter
# -----------------------------------------------------------------------------

def test_init_success(temp_token_file):
    """정상적인 초기화 상태를 테스트합니다."""
    adapter = GoogleDriveAdapter(token_file=temp_token_file, folders={"test_folder": "id_123"})
    assert adapter.token_file == temp_token_file
    assert adapter.folders == {"test_folder": "id_123"}
    assert adapter.client_secret_file is None


def test_init_missing_token_file():
    """token_file 인자가 아예 생략되거나 빈 값일 때의 예외 발생을 테스트합니다."""
    with pytest.raises(ValueError, match="token_file must be provided."):
        GoogleDriveAdapter(token_file="")


def test_init_file_not_found():
    """존재하지 않는 token_file 경로가 제공되었을 때의 예외 발생을 테스트합니다."""
    with pytest.raises(FileNotFoundError, match="Token file not found"):
        GoogleDriveAdapter(token_file="non_existent_token.json")


def test_service_property_fresh(temp_token_file, mock_drive_service):
    """토큰이 만료되지 않은 경우 갱신 과정 없이 API 서비스를 빌드하는지 확인합니다."""
    adapter = GoogleDriveAdapter(token_file=temp_token_file)
    service = adapter.service
    assert service == mock_drive_service


def test_service_property_expired_refresh(temp_token_file, mock_drive_service):
    """토큰이 만료되었을 때 갱신(Refresh) 로직이 수행되고 파일에 갱신 결과가 쓰여지는지 테스트합니다."""
    adapter = GoogleDriveAdapter(token_file=temp_token_file)

    mock_creds = MagicMock()
    mock_creds.expired = True
    mock_creds.refresh_token = "some_refresh_token"
    mock_creds.to_json.return_value = '{"token": "refreshed_oauth_token"}'
    mock_creds.universe_domain = "googleapis.com"

    with patch("google.oauth2.credentials.Credentials.from_authorized_user_file", return_value=mock_creds), \
         patch("googleapiclient.discovery.build", return_value=mock_drive_service) as mock_build, \
         patch("evenezer.infrastructure.adapters.google.google_drive_adapter.Request") as mock_request:
        
        service = adapter.service
        assert service == mock_drive_service
        mock_creds.refresh.assert_called_once_with(mock_request.return_value)
        
        with open(temp_token_file, "r") as f:
            assert "refreshed_oauth_token" in f.read()


def test_get_root_id_cases(temp_token_file):
    """folders 상태에 따른 _get_root_id 분기 처리들을 검증합니다."""
    # 1. 단일 폴더 셋업 시 folder 생략 허용
    adapter = GoogleDriveAdapter(token_file=temp_token_file, folders={"my_folder": "root_id_1"})
    assert adapter._get_root_id() == "root_id_1"

    # 2. 다중 폴더 셋업 시 folder 생략 시 ValueError 발생
    adapter_multi = GoogleDriveAdapter(token_file=temp_token_file, folders={"f1": "id_1", "f2": "id_2"})
    with pytest.raises(ValueError, match="Multiple folders available"):
        adapter_multi._get_root_id()

    # 3. 존재하지 않는 folder 명시 시 ValueError 발생
    with pytest.raises(ValueError, match="Folder keyword 'f3' not found"):
        adapter_multi._get_root_id(folder="f3")

    # 4. 올바른 folder 명시 시 ID 리턴
    assert adapter_multi._get_root_id(folder="f1") == "id_1"


def test_authenticate_success_and_fail(temp_token_file, mock_drive_service):
    """_authenticate API 성공 및 예외 처리 흐름을 테스트합니다."""
    adapter = GoogleDriveAdapter(token_file=temp_token_file)

    mock_creds = MagicMock()
    mock_creds.expired = False
    mock_creds.universe_domain = "googleapis.com"

    # 성공 케이스
    with patch("google.oauth2.credentials.Credentials.from_authorized_user_file", return_value=mock_creds), \
         patch("googleapiclient.discovery.build", return_value=mock_drive_service):
        
        service = adapter._authenticate()
        assert service == mock_drive_service

    # 실패 케이스 (예외 발생)
    with patch("google.oauth2.credentials.Credentials.from_authorized_user_file", side_effect=Exception("Auth error")):
        with pytest.raises(RuntimeError, match="Google Drive 인증 실패"):
            adapter._authenticate()


def test_get_or_create_folder_exists(temp_token_file, mock_drive_service):
    """이미 폴더가 존재하는 경우 조회를 통해 기존 ID를 반환하는지 테스트합니다."""
    adapter = GoogleDriveAdapter(token_file=temp_token_file, folders={"root": "root_id"})
    
    mock_drive_service.files()._list_res.execute.return_value = {"files": [{"id": "existing_folder_id", "name": "my_folder"}]}
    
    folder_id = adapter._get_or_create_folder("my_folder", "root_id")
    assert folder_id == "existing_folder_id"
    mock_drive_service.files()._list_res.execute.assert_called_once()
    mock_drive_service.files()._create_res.execute.assert_not_called()


def test_get_or_create_folder_not_exists(temp_token_file, mock_drive_service):
    """폴더가 없을 때 신규 폴더를 생성하고 신규 ID를 반환하는지 테스트합니다."""
    adapter = GoogleDriveAdapter(token_file=temp_token_file, folders={"root": "root_id"})

    mock_drive_service.files()._list_res.execute.return_value = {"files": []}
    mock_drive_service.files()._create_res.execute.return_value = {"id": "new_folder_id"}

    folder_id = adapter._get_or_create_folder("my_folder", "root_id")
    assert folder_id == "new_folder_id"
    mock_drive_service.files()._list_res.execute.assert_called_once()
    mock_drive_service.files()._create_res.execute.assert_called_once()


def test_get_file_id_nfc_nfd_normalization(temp_token_file, mock_drive_service):
    """한글 유니코드 정규화(NFC, NFD) 차이에도 파일을 정상적으로 대조하여 ID를 구하는지 테스트합니다."""
    adapter = GoogleDriveAdapter(token_file=temp_token_file, folders={"root": "root_id"})

    import unicodedata
    nfd_name = unicodedata.normalize("NFD", "한글")
    nfc_name = unicodedata.normalize("NFC", "한글")

    mock_drive_service.files()._list_res.execute.return_value = {
        "files": [{"id": "file_123", "name": nfd_name, "mimeType": "application/octet-stream"}]
    }

    file_id = adapter._get_file_id(path=f"{nfc_name}", folder="root")
    assert file_id == "file_123"


def test_get_file_id_not_found(temp_token_file, mock_drive_service):
    """파일이 존재하지 않을 때 None을 정상 반환하는지 테스트합니다."""
    adapter = GoogleDriveAdapter(token_file=temp_token_file, folders={"root": "root_id"})

    mock_drive_service.files()._list_res.execute.return_value = {"files": []}

    file_id = adapter._get_file_id("non_existent_file.txt", folder="root")
    assert file_id is None


def test_ensure_path_directories(temp_token_file, mock_drive_service):
    """상위 폴더 트리를 생성하고 마지막 부모 폴더 ID를 리턴하는지 테스트합니다."""
    adapter = GoogleDriveAdapter(token_file=temp_token_file, folders={"root": "root_id"})

    with patch.object(adapter, "_get_or_create_folder", side_effect=["dir1_id", "dir2_id"]) as mock_create:
        parent_id = adapter._ensure_path_directories("sub1/sub2/file.txt", folder="root")
        assert parent_id == "dir2_id"
        assert mock_create.call_count == 2
        mock_create.assert_any_call("sub1", "root_id")
        mock_create.assert_any_call("sub2", "dir1_id")


@pytest.mark.asyncio
async def test_get_file_success(temp_token_file, mock_drive_service):
    """파일 정상 다운로드 시나리오를 테스트합니다."""
    adapter = GoogleDriveAdapter(token_file=temp_token_file, folders={"root": "root_id"})

    with patch.object(adapter, "_get_file_id", return_value="file_id_abc"):
        result = await adapter.get_file("test.txt", folder="root")
        assert result == b"mocked_data_bytes"


@pytest.mark.asyncio
async def test_get_file_not_found(temp_token_file, mock_drive_service):
    """파일 ID가 없는 경우 None을 리턴하는지 검증합니다."""
    adapter = GoogleDriveAdapter(token_file=temp_token_file, folders={"root": "root_id"})

    with patch.object(adapter, "_get_file_id", return_value=None):
        result = await adapter.get_file("test.txt", folder="root")
        assert result is None


@pytest.mark.asyncio
async def test_get_file_exception(temp_token_file, mock_drive_service):
    """다운로드 처리 중 예외 발생 시 None을 반환하는지 테스트합니다."""
    adapter = GoogleDriveAdapter(token_file=temp_token_file, folders={"root": "root_id"})

    with patch.object(adapter, "_get_file_id", return_value="file_id_abc"), \
         patch.object(mock_drive_service.files(), "get_media", side_effect=Exception("Download API failed")):
        
        result = await adapter.get_file("test.txt", folder="root")
        assert result is None


@pytest.mark.asyncio
async def test_put_file_success_and_mime_types(temp_token_file, mock_drive_service):
    """확장자별 Mime-Type 매핑 및 put_file 업로드 성공 시나리오를 테스트합니다."""
    adapter = GoogleDriveAdapter(token_file=temp_token_file, folders={"root": "root_id"})

    with patch.object(adapter, "_upload_file") as mock_upload:
        # 1. xlsx
        assert await adapter.put_file("report.xlsx", b"data", folder="root") is True
        mock_upload.assert_called_with(ANY, "report.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", folder="root", root_id=None)

        # 2. csv
        assert await adapter.put_file("report.csv", b"data", folder="root") is True
        mock_upload.assert_called_with(ANY, "report.csv", "text/csv", folder="root", root_id=None)

        # 3. pdf
        assert await adapter.put_file("report.pdf", b"data", folder="root") is True
        mock_upload.assert_called_with(ANY, "report.pdf", "application/pdf", folder="root", root_id=None)

        # 4. default octet-stream
        assert await adapter.put_file("report.bin", b"data", folder="root") is True
        mock_upload.assert_called_with(ANY, "report.bin", "application/octet-stream", folder="root", root_id=None)


@pytest.mark.asyncio
async def test_put_file_exception(temp_token_file, mock_drive_service):
    """업로드 도중 예외가 발생할 때 False를 리턴하는지 테스트합니다."""
    adapter = GoogleDriveAdapter(token_file=temp_token_file, folders={"root": "root_id"})

    with patch.object(adapter, "_upload_file", side_effect=Exception("Upload Error")):
        result = await adapter.put_file("report.bin", b"data", folder="root")
        assert result is False


def test_upload_file_new_and_update(temp_token_file, mock_drive_service):
    """기존 파일이 있을 때 update, 없을 때 create를 타는지 검증합니다."""
    adapter = GoogleDriveAdapter(token_file=temp_token_file, folders={"root": "root_id"})

    with patch.object(adapter, "_ensure_path_directories", return_value="parent_id"), \
         patch("evenezer.infrastructure.adapters.google.google_drive_adapter.MediaIoBaseUpload") as mock_upload_cls:
        
        # 1. 파일이 존재하는 경우 (update)
        mock_drive_service.files()._list_res.execute.return_value = {"files": [{"id": "existing_file_id"}]}
        
        data_stream = io.BytesIO(b"data")
        adapter._upload_file(data_stream, "test.txt", "text/plain", folder="root")
        
        mock_drive_service.files()._update_res.execute.assert_called_once()
        mock_drive_service.files()._create_res.execute.assert_not_called()

        # 2. 파일이 존재하지 않는 경우 (create)
        mock_drive_service.files()._list_res.execute.reset_mock()
        mock_drive_service.files()._update_res.execute.reset_mock()
        mock_drive_service.files()._create_res.execute.reset_mock()
        
        mock_drive_service.files()._list_res.execute.return_value = {"files": []}
        
        data_stream.seek(0)
        adapter._upload_file(data_stream, "test.txt", "text/plain", folder="root")
        
        mock_drive_service.files()._create_res.execute.assert_called_once()
        mock_drive_service.files()._update_res.execute.assert_not_called()


@pytest.mark.asyncio
async def test_path_exists_and_ensure_directory(temp_token_file, mock_drive_service):
    """path_exists와 ensure_directory의 성공 및 실패 케이스를 검증합니다."""
    adapter = GoogleDriveAdapter(token_file=temp_token_file, folders={"root": "root_id"})

    with patch.object(adapter, "_get_file_id", side_effect=["file_id_exists", None]):
        assert await adapter.path_exists("test.txt", folder="root") is True
        assert await adapter.path_exists("missing.txt", folder="root") is False

    with patch.object(adapter, "_ensure_path_directories", side_effect=[None, Exception("Ensure directory fail")]):
        assert await adapter.ensure_directory("my/dir", folder="root") is True
        assert await adapter.ensure_directory("my/dir_err", folder="root") is False


@pytest.mark.asyncio
async def test_list_files_in_folder_success(temp_token_file, mock_drive_service):
    """폴더 내 파일 목록을 정상적으로 리스트업하는지 테스트합니다."""
    adapter = GoogleDriveAdapter(token_file=temp_token_file, folders={"root": "root_id"})

    with patch.object(adapter, "_get_file_id", return_value="folder_id_123"):
        mock_files = [{"id": "f1", "name": "a.pdf"}, {"id": "f2", "name": "b.pdf"}]
        mock_drive_service.files()._list_res.execute.return_value = {"files": mock_files}

        result = await adapter.list_files_in_folder("my_folder")
        assert len(result) == 2
        assert result == mock_files
        mock_drive_service.files()._list_mock.assert_called_with(
            q="'folder_id_123' in parents and trashed = false",
            fields="files(id, name, mimeType, size, createdTime, modifiedTime, md5Checksum)",
            pageSize=1000,
        )


@pytest.mark.asyncio
async def test_list_files_in_folder_missing_and_exception(temp_token_file, mock_drive_service):
    """폴더가 없거나 예외 발생 시 빈 리스트를 리턴하는지 테스트합니다."""
    adapter = GoogleDriveAdapter(token_file=temp_token_file, folders={"root": "root_id"})

    # 1. 폴더 ID 조회 실패
    with patch.object(adapter, "_get_file_id", return_value=None):
        result = await adapter.list_files_in_folder("my_folder")
        assert result == []

    # 2. list API 실행 예외
    with patch.object(adapter, "_get_file_id", return_value="folder_id_123"):
        mock_drive_service.files()._list_res.execute.side_effect = Exception("API error")
        result = await adapter.list_files_in_folder("my_folder")
        assert result == []


@pytest.mark.asyncio
async def test_list_files_keyword(temp_token_file, mock_drive_service):
    """list_files 단축 키워드 메서드 호출을 테스트합니다."""
    adapter = GoogleDriveAdapter(token_file=temp_token_file, folders={"root": "root_id"})

    with patch.object(adapter, "list_files_in_folder", return_value=[{"id": "file"}]) as mock_list:
        result = await adapter.list_files("root")
        assert result == [{"id": "file"}]
        mock_list.assert_called_once_with("", folder="root")


@pytest.mark.asyncio
async def test_get_file_by_id_spreadsheet_vs_normal(temp_token_file, mock_drive_service):
    """Google Sheets 포맷일 때 export_media를 호출하고 일반 파일일 때 get_media를 호출하는지 검증합니다."""
    adapter = GoogleDriveAdapter(token_file=temp_token_file)

    # 1. 구글 스프레드시트 포맷
    mock_drive_service.files()._get_res.execute.return_value = {"mimeType": "application/vnd.google-apps.spreadsheet"}
    
    await adapter.get_file_by_id("sheet_id_123")
    mock_drive_service.files()._export_media_mock.assert_called_with(
        fileId="sheet_id_123",
        mimeType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    mock_drive_service.files()._get_media_mock.assert_not_called()

    # 2. 일반 파일 포맷
    mock_drive_service.files()._get_media_mock.reset_mock()
    mock_drive_service.files()._get_res.execute.return_value = {"mimeType": "application/pdf"}

    await adapter.get_file_by_id("pdf_id_123")
    mock_drive_service.files()._get_media_mock.assert_called_with(fileId="pdf_id_123")


@pytest.mark.asyncio
async def test_get_file_by_id_exception(temp_token_file, mock_drive_service):
    """파일 ID 다운로드 중 예외 발생 시 None을 리턴하는지 테스트합니다."""
    adapter = GoogleDriveAdapter(token_file=temp_token_file)

    mock_drive_service.files()._get_res.execute.side_effect = Exception("File deleted")
    
    result = await adapter.get_file_by_id("err_id")
    assert result is None


@pytest.mark.asyncio
async def test_get_file_metadata_and_delete_file(temp_token_file, mock_drive_service):
    """get_file_metadata와 delete_file의 성공, 실패, 예외 처리를 검증합니다."""
    adapter = GoogleDriveAdapter(token_file=temp_token_file, folders={"root": "root_id"})

    # 1. 메타데이터 조회 성공 및 예외
    mock_drive_service.files()._get_res.execute.return_value = {"id": "f123", "name": "test"}
    meta = await adapter.get_file_metadata("f123")
    assert meta == {"id": "f123", "name": "test"}
    mock_drive_service.files()._get_mock.assert_called_with(
        fileId="f123", fields="id, name, modifiedTime, size, mimeType, md5Checksum"
    )

    mock_drive_service.files()._get_res.execute.side_effect = Exception("Meta API error")
    assert await adapter.get_file_metadata("f123") is None

    # 2. 파일 삭제 성공, 부재, 예외
    mock_drive_service.files()._get_res.execute.reset_mock()
    with patch.object(adapter, "_get_file_id", side_effect=["file_id_to_del", None, "file_id_err"]):
        # 삭제 성공
        assert await adapter.delete_file("del.txt", folder="root") is True
        mock_drive_service.files()._delete_res.execute.assert_called_once()

        # 파일 부재
        assert await adapter.delete_file("missing.txt", folder="root") is False

        # 예외 발생
        mock_drive_service.files()._delete_res.execute.side_effect = Exception("Delete API failed")
        assert await adapter.delete_file("err.txt", folder="root") is False


@pytest.mark.asyncio
async def test_sync_pdf_reports(temp_token_file, tmp_path):
    """pdf 동기화 시 로컬 파일 대조를 통해 새 파일만 골라 업로드되는지 테스트합니다."""
    adapter = GoogleDriveAdapter(token_file=temp_token_file)

    local_dir = tmp_path / "pdf_reports"
    local_dir.mkdir()
    
    (local_dir / "report1.pdf").write_bytes(b"pdf1")
    (local_dir / "report2.pdf").write_bytes(b"pdf2")

    drive_mock_files = [{"name": "report1.pdf", "id": "d1"}]

    with patch.object(adapter, "list_files_in_folder", return_value=drive_mock_files), \
         patch.object(adapter, "put_file", return_value=True) as mock_put:
        
        await adapter.sync_pdf_reports(str(local_dir), "drive_pdf_folder")
        mock_put.assert_called_once_with("drive_pdf_folder/report2.pdf", b"pdf2")


@pytest.mark.asyncio
async def test_sync_pdf_reports_no_local_dir(temp_token_file):
    """로컬 디렉터리가 존재하지 않을 때 조기 리턴되는지 테스트합니다."""
    adapter = GoogleDriveAdapter(token_file=temp_token_file)

    with patch.object(adapter, "list_files_in_folder", return_value=[]) as mock_list:
        await adapter.sync_pdf_reports("non_existent_folder", "drive_pdf")
        mock_list.assert_called_once_with("drive_pdf")


@pytest.mark.asyncio
async def test_download_file_success_and_fail(temp_token_file, tmp_path, mock_drive_service):
    """download_file의 원자적 교체(.tmp 사용) 및 다운로드 도중 실패 상황을 검증합니다."""
    adapter = GoogleDriveAdapter(token_file=temp_token_file, folders={"root": "root_id"})
    dest_file = tmp_path / "downloaded.pdf"

    # 1. 성공 케이스
    mock_drive_service.files()._list_res.execute.return_value = {"files": [{"id": "down_id"}]}

    success = await adapter.download_file("filename.pdf", dest_file, folder="root")
    assert success is True
    assert dest_file.exists()
    assert dest_file.read_bytes() == b"mocked_data_bytes"

    # 2. 다운로드 도중 예외 발생 시 .tmp 파일 자동 삭제 확인
    class MockExceptionDownloader:
        def __init__(self, *args, **kwargs):
            raise Exception("Download break")

    with patch("evenezer.infrastructure.adapters.google.google_drive_adapter.MediaIoBaseDownload", new=MockExceptionDownloader):
        dest_file.unlink(missing_ok=True)
        success_fail = await adapter.download_file("filename.pdf", dest_file, folder="root")
        assert success_fail is False
        assert not dest_file.exists()
        
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0


def test_download_missing_reports_full_flow(temp_token_file, tmp_path, mock_drive_service):
    """ThreadPoolExecutor 기반 병렬 다운로드와 진행률 콜백, 필터링 흐름을 검증합니다."""
    adapter = GoogleDriveAdapter(token_file=temp_token_file)

    local_dir = tmp_path / "reports"
    local_dir.mkdir()
    
    (local_dir / "already.pdf").write_bytes(b"old")
    
    report_list = [
        {"filename": "already.pdf"},
        {"filename": "missing1.pdf"},
        {"filename": "missing2.pdf"},
    ]

    mock_callback = MagicMock()

    mock_drive_service.files()._list_res.execute.return_value = {"files": [{"id": "mock_id"}]}
    
    adapter.download_missing_reports(str(local_dir), report_list, progress_callback=mock_callback)

    assert (local_dir / "missing1.pdf").exists()
    assert (local_dir / "missing2.pdf").exists()
    assert (local_dir / "missing1.pdf").read_bytes() == b"mocked_data_bytes"

    assert mock_callback.call_count >= 2
    mock_callback.assert_any_call(ANY, 1.0)


def test_download_missing_reports_all_exists(temp_token_file, tmp_path):
    """모든 다운로드 대상이 로컬에 이미 존재할 때, 즉시 리턴하고 콜백을 전달하는지 검증합니다."""
    adapter = GoogleDriveAdapter(token_file=temp_token_file)
    local_dir = tmp_path / "reports_all"
    local_dir.mkdir()
    (local_dir / "exists.pdf").write_bytes(b"data")

    report_list = [{"filename": "exists.pdf"}]
    mock_callback = MagicMock()

    with patch("evenezer.infrastructure.adapters.google.google_drive_adapter.build") as mock_build:
        adapter.download_missing_reports(str(local_dir), report_list, progress_callback=mock_callback)
        mock_build.assert_not_called()
        mock_callback.assert_called_once_with("모든 리포트가 로컬에 존재합니다. (총 1개)", 1.0)
