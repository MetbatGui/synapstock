import logging
import pytest
from synapstock.infrastructure.container import Container

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@pytest.mark.asyncio
async def test_weekly_change_config_loading():
    """WeeklyChangeService가 컨테이너에서 올바르게 초기화되는지 확인한다."""
    container = Container()
    service = container.weekly_change_service
    
    assert service is not None
    assert service.get_service_name() == "WeeklyChangeService"
    assert service.folder_id == container.config.weekly_change_folder_id

@pytest.mark.asyncio
async def test_weekly_change_sync_logic_subfolder_mock(monkeypatch):
    """하위 폴더(연도/월)에서 파일을 찾는 로직을 테스트한다."""
    container = Container()
    service = container.weekly_change_service
    
    list_calls = []

    async def mock_list_files(folder_path, **kwargs):
        list_calls.append(folder_path)
        if folder_path in ("2026/05", "2026/05월"):
            return [{"id": "file_sub", "name": "weekly_gainers_2026_W19_05M1W_0504~0508.xlsx"}]
        return [] # 루트 등 다른 폴더엔 없음
        
    async def mock_get_file(filename, **kwargs):
        import pandas as pd
        import io
        df = pd.DataFrame([{"종목명": "삼성전자", "현재가": 70000, "전주종가": 68000, "등락률": 2.94}])
        out = io.BytesIO()
        df.to_excel(out, index=False)
        return out.getvalue()

    class MockDriveAdapter:
        async def list_files_in_folder(self, folder_path, **kwargs):
            return await mock_list_files(folder_path, **kwargs)
        async def get_file(self, filename, **kwargs):
            return await mock_get_file(filename, **kwargs)

    mock_adapter = MockDriveAdapter()
    monkeypatch.setattr(service, "drive_adapter", mock_adapter)
    # 2026-05-08 날짜로 동기화 시도 -> 2026/05 폴더 검색 기대
    report = await service.sync_data("2026-05-08")
    
    assert report is not None
    assert any("2026/05" in call for call in list_calls)
    assert report.date == "2026-05-08"
    assert report.month == 5
    assert report.week_of_month == 1
    assert report.items[0].name == "삼성전자"
