import pytest

def pytest_collection_modifyitems(items):
    """테스트가 위치한 디렉토리에 따라 자동으로 unit 또는 integration 마커를 부여합니다.
    
    - tests/unit 디렉토리 내부: @pytest.mark.unit
    - tests/integration 디렉토리 내부: @pytest.mark.integration
    """
    for item in items:
        # 파일의 절대 경로를 가져와서 체크 (문자열 매칭)
        path = str(item.fspath)
        
        if "tests/unit" in path.replace("\\", "/"):
            item.add_marker(pytest.mark.unit)
        elif "tests/integration" in path.replace("\\", "/"):
            item.add_marker(pytest.mark.integration)
