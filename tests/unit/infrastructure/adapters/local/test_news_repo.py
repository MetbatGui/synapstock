import pytest
import json
from pathlib import Path
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

    def test_load_non_existent_batch(self, repo):
        """존재하지 않는 날짜 로드 시 None을 반환해야 한다."""
        assert repo.load_batch("1999-01-01") is None
