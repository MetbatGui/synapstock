
import pytest

from synapstock.domain.news.models import NewsBatch, NewsItem
from synapstock.infrastructure.adapters.local.news_repo import LocalNewsRepository


@pytest.fixture
def temp_news_dir(tmp_path):
    """테스트용 임시 뉴스 디렉토리 제공."""
    d = tmp_path / "news"
    d.mkdir()
    return d

@pytest.fixture
def repo(temp_news_dir):
    return LocalNewsRepository(temp_news_dir)

class TestLocalNewsRepository:
    def test_save_and_load_batch(self, repo, temp_news_dir):
        """배치를 저장하고 다시 로드했을 때 데이터가 일치해야 한다."""
        date_str = "2024-04-23"
        item = NewsItem(
            id="hash123",
            title="테스트",
            url="http://test.com"
        )
        batch = NewsBatch(date=date_str, items=[item])

        # 저장
        assert repo.save_batch(batch) is True

        # 파일 존재 확인
        expected_file = temp_news_dir / f"news_{date_str}.json"
        assert expected_file.exists()

        # 로드
        loaded = repo.load_batch(date_str)
        assert loaded is not None
        assert loaded.date == date_str
        assert len(loaded.items) == 1
        assert loaded.items[0].title == "테스트"

    def test_list_available_dates(self, repo, temp_news_dir):
        """저장된 파일들로부터 날짜 목록을 정확히 가져와야 한다."""
        # 더미 파일 생성
        (temp_news_dir / "news_2024-04-21.json").touch()
        (temp_news_dir / "news_2024-04-22.json").touch()
        (temp_news_dir / "other_file.txt").touch()

        dates = repo.list_available_dates()

        assert len(dates) == 2
        assert "2024-04-22" in dates
        assert "2024-04-21" in dates
        # 역순 정렬 확인
        assert dates[0] == "2024-04-22"

    def test_list_available_dates_excludes_metadata(self, repo, temp_news_dir):
        """news_metadata.json 파일은 날짜 목록에서 제외되어야 한다."""
        (temp_news_dir / "news_2024-04-21.json").touch()
        (temp_news_dir / "news_metadata.json").touch()

        dates = repo.list_available_dates()

        assert "2024-04-21" in dates
        assert "metadata" not in str(dates)
        assert len(dates) == 1

    def test_get_all_batch_files_excludes_metadata(self, repo, temp_news_dir):
        """get_all_batch_files는 news_metadata.json을 제외해야 한다."""
        (temp_news_dir / "news_2024-04-21.json").touch()
        (temp_news_dir / "news_metadata.json").touch()

        files = repo.get_all_batch_files()
        
        filenames = [f.name for f in files]
        assert "news_2024-04-21.json" in filenames
        assert "news_metadata.json" not in filenames
        assert len(files) == 1

    def test_save_raw_file(self, repo, temp_news_dir):
        """save_raw_file이 파일 내용을 저장하고 시각을 설정해야 한다."""
        filename = "raw_test.json"
        content = b"raw_content"
        mtime = 1713873600.0 # 2024-04-23
        
        repo.save_raw_file(filename, content, mtime=mtime)
        
        path = temp_news_dir / filename
        assert path.exists()
        assert path.read_bytes() == content
        assert path.stat().st_mtime == mtime

    def test_sync_metadata_flow(self, repo, temp_news_dir):
        """메타데이터 저장 및 로드 흐름을 검증한다."""
        metadata = {"file1.json": "2024-04-23T12:00:00Z"}
        
        # 저장
        repo.save_sync_metadata(metadata)
        assert (temp_news_dir / "news_metadata.json").exists()
        
        # 로드
        loaded = repo.load_sync_metadata()
        assert loaded == metadata

    def test_load_non_existent_metadata(self, repo):
        """메타데이터가 없을 때 빈 딕셔너리를 반환해야 한다."""
        assert repo.load_sync_metadata() == {}

    def test_load_non_existent_batch(self, repo):
        """존재하지 않는 날짜 로드 시 None을 반환해야 한다."""
        assert repo.load_batch("1999-01-01") is None
