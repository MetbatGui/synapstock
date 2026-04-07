import pytest
from pathlib import Path
import shutil
from synapstock.infrastructure.adapters.local.file_storage import LocalFileStorageAdapter

@pytest.fixture
def temp_storage_dir(tmp_path):
    """테스트를 위한 임시 디렉토리를 생성한다."""
    d = tmp_path / "storage_test"
    d.mkdir()
    return d

@pytest.fixture
def storage(temp_storage_dir):
    """LocalFileStorageAdapter 인스턴스를 생성한다."""
    return LocalFileStorageAdapter(base_dir=temp_storage_dir)

class TestLocalFileStorageAdapter:
    """LocalFileStorageAdapter 단위 테스트."""

    def test_put_and_get_file(self, storage):
        """파일을 저장하고 다시 읽을 수 있어야 한다.

        Arrange:
            저장할 데이터와 경로를 준비한다.
        Act:
            put_file()로 저장 후 get_file()로 읽는다.
        Assert:
            읽어온 데이터가 원본과 일치하는지 확인한다.
        """
        data = b"hello world"
        path = "test.txt"
        
        storage.put_file(path, data)
        read_data = storage.get_file(path)
        
        assert read_data == data

    def test_ensure_directory(self, storage):
        """디렉토리 생성을 보장해야 한다.

        Arrange:
            생성할 디렉토리 경로를 준비한다.
        Act:
            ensure_directory()를 호출한다.
        Assert:
            실제 디렉토리가 존재하고 path_exists()가 True인지 확인한다.
        """
        dir_path = "subdir/inner"
        
        success = storage.ensure_directory(dir_path)
        
        assert success is True
        assert storage.path_exists(dir_path) is True

    def test_list_files_in_folder(self, storage):
        """폴더 내 파일 목록을 정확히 반환해야 한다.

        Arrange:
            특정 폴더에 파일 2개를 생성한다.
        Act:
            list_files_in_folder()를 호출한다.
        Assert:
            반환된 목록의 길이가 2이며 파일명이 포함되어 있는지 확인한다.
        """
        storage.put_file("folder/file1.txt", b"1")
        storage.put_file("folder/file2.txt", b"2")
        
        files = storage.list_files_in_folder("folder")
        
        assert len(files) == 2
        names = [f["name"] for f in files]
        assert "file1.txt" in names
        assert "file2.txt" in names

    def test_download_file_copy(self, storage, tmp_path):
        """파일을 특정 로컬 경로로 복사(다운로드)할 수 있어야 한다.

        Arrange:
            저장소에 소스 파일을 생성하고 대상 경로를 준비한다.
        Act:
            download_file()을 호출한다.
        Assert:
            대상 경로에 파일이 존재하고 내용이 일치하는지 확인한다.
        """
        storage.put_file("source.txt", b"content")
        dest_path = tmp_path / "dest.txt"
        
        success = storage.download_file("source.txt", str(dest_path))
        
        assert success is True
        assert dest_path.exists()
        assert dest_path.read_bytes() == b"content"

    def test_get_non_existent_file(self, storage):
        """존재하지 않는 파일 요청 시 None을 반환해야 한다.

        Arrange:
            존재하지 않는 경로를 준비한다.
        Act:
            get_file()을 호출한다.
        Assert:
            결과가 None인지 확인한다.
        """
        result = storage.get_file("no_such_file.txt")
        assert result is None
