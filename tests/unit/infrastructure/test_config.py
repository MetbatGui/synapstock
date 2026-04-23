import os
from pathlib import Path
from unittest.mock import patch

from synapstock.infrastructure.config import AppConfig


def test_config_load_default_paths():
    """기본 경로 설정이 올바르게 로드되는지 확인한다.

    Arrange: 환경 변수가 비어있는 상태를 가정한다.
    Act: AppConfig.load()를 호출한다.
    Assert: 기본 데이터 및 비밀번호 디렉토리가 예상한 대로인지 확인한다.
    """
    with patch.dict(os.environ, {}, clear=True):
        config = AppConfig.load(load_env=False)

        assert config.data_dir == Path("data")
        assert config.secrets_dir == Path("secrets")
        assert config.board_dir == Path("data/board")
        assert config.report_dir == Path("data/report")

def test_config_load_from_env():
    """환경 변수로부터 토큰과 폴더 ID를 올바르게 로드하는지 확인한다.

    Arrange: 필요한 환경 변수를 모의(Mock)로 설정한다.
    Act: AppConfig.load()를 호출한다.
    Assert: 각 필드에 환경 변수 값이 올바르게 매핑되었는지 확인한다.
    """
    mock_env = {
        "MIRO_ACCESS_TOKEN": "miro_token_123",
        "TELEGRAM_API_TOKEN": "bot_token_456",
        "GOOGLE_DRIVE_REPORT_FOLDER_ID": "report_id_789",
        "DATA_DIR": "custom_data"
    }

    with patch.dict(os.environ, mock_env):
        config = AppConfig.load(load_env=False)

        assert config.miro_token == "miro_token_123"
        assert config.telegram_token == "bot_token_456"
        assert config.report_folder_id == "report_id_789"
        assert config.data_dir == Path("custom_data")
        # DATA_DIR 변경 시 하위 경로도 변경되어야 함
        assert config.board_dir == Path("custom_data/board")

def test_config_optional_fields():
    """선택적 필드(폴더 ID)가 없을 때 None을 반환하는지 확인한다.

    Arrange: 필수 환경 변수만 설정한다.
    Act: AppConfig.load()를 호출한다.
    Assert: 선택 필드가 None인지 확인한다.
    """
    with patch.dict(os.environ, {}, clear=True):
        config = AppConfig.load(load_env=False)
        assert config.report_folder_id is None
        assert config.sd_folder_id is None
