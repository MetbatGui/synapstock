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
async def test_weekly_change_sync_logic_mock(monkeypatch):
    """실제 Drive 연결 없이 동기화 로직의 흐름을 테스트한다."""
    container = Container()
    service = container.weekly_change_service
    
    # Drive 어댑터의 동작을 모의(Mock) 처리
    async def mock_list_files(*args, **kwargs):
        return [{"id": "file_123", "name": "weekly_gainers_2026_W19_05M1W_0504~0508.xlsx"}]
        
    async def mock_get_file(*args, **kwargs):
        import pandas as pd
        import io
        df = pd.DataFrame([{"종목명": "삼성전자", "현재가": 70000, "전주종가": 68000, "등락률": 2.94}])
        out = io.BytesIO()
        df.to_excel(out, index=False)
        return out.getvalue()

    if service.drive_adapter:
        monkeypatch.setattr(service.drive_adapter, "list_files_in_folder", mock_list_files)
        monkeypatch.setattr(service.drive_adapter, "get_file", mock_get_file)
        
        # date_str을 명시하지 않으면 파일명에서 추출함 (2026-05-08)
        report = await service.sync_data()
        
        assert report is not None
        assert report.date == "2026-05-08"
        assert report.year == 2026
        assert report.month == 5
        assert report.week_of_month == 1
        assert report.week_num == 19
        assert report.date_range == "0504~0508"
        assert len(report.items) > 0
        assert report.items[0].name == "삼성전자"
        assert report.items[0].change_rate == 2.94
