import pytest

from evenezer.infrastructure.container import Container
from evenezer.infrastructure.persistence.weekly_change_db_sync import WeeklyChangeDbSync


@pytest.mark.asyncio
async def test_weekly_change_config_loading():
    """WeeklyChangeService가 컨테이너에서 올바르게 초기화되는지 확인한다."""
    container = Container()
    service = container.weekly_change_service

    assert service is not None
    assert service.get_service_name() == "WeeklyChangeService"
    assert service.folder_id == container.config.weekly_change_folder_id
    assert isinstance(service.db_sync, WeeklyChangeDbSync)
    assert service.db_sync.drive_adapter is container.drive_adapter
