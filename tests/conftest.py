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


@pytest.fixture
def integration_test_env():
    """통합 테스트를 위해 DATA_DIR 환경 변수를 임시 디렉터리로 전환하고,
    fixtures 데이터를 복사한 후 container 설정을 재초기화합니다.
    """
    import os
    import shutil
    import tempfile
    from pathlib import Path
    from synapstock.infrastructure.container import container

    # 1. 임시 디렉터리 생성 및 DATA_DIR 설정
    temp_dir = Path(tempfile.mkdtemp(prefix="synapstock_integration_"))
    old_data_dir = os.environ.get("DATA_DIR")
    os.environ["DATA_DIR"] = str(temp_dir)

    # 2. 구글 드라이브/미로 연동 방지를 위해 테스트 중 관련 환경 변수 비우기
    google_vars = [
        "GOOGLE_DRIVE_REPORT_FOLDER_ID", "GOOGLE_DRIVE_SUPPLY_DEMAND_FOLDER_ID",
        "GOOGLE_DRIVE_CEILLING_FOLDER_ID", "GOOGLE_DRIVE_CAPITAL_INCREASE_FOLDER_ID",
        "GOOGLE_DRIVE_BONUS_SHARE_FOLDER_ID", "GOOGLE_DRIVE_CONVERTIBLE_BOND_FOLDER_ID",
        "GOOGLE_DRIVE_BW_FOLDER_ID", "GOOGLE_DRIVE_NEW_LISTING_FOLDER_ID",
        "GOOGLE_DRIVE_NEWS_FOLDER_ID", "GOOGLE_DRIVE_WEEKLY_CHANGE_ID",
        "GOOGLE_DRIVE_THEME_FOLDER_ID", "GOOGLE_DRIVE_FINANCIAL_STATEMENTS_ID",
        "GOOGLE_DRIVE_STOCK_SPLIT_ID"
    ]
    old_google_env = {}
    for var in google_vars:
        old_google_env[var] = os.environ.get(var)
        os.environ[var] = ""

    # 3. 템플릿 데이터 복사
    # 프로젝트 루트의 tests/fixtures 디렉터리
    fixtures_dir = Path(__file__).parent / "fixtures"
    if fixtures_dir.exists():
        # fixtures 디렉터리 내의 서브폴더들을 임시 DATA_DIR 내에 그대로 복사
        if (fixtures_dir / "boards").exists():
            board_dest = temp_dir / "board"
            board_dest.mkdir(parents=True, exist_ok=True)
            for file_path in (fixtures_dir / "boards").glob("*.json"):
                dest_name = file_path.name
                # LocalBoardRepository.list_boards() 필터에 걸리도록 theme_ 접두사 부여
                if not dest_name.startswith("theme_") and not dest_name.startswith("virtual_"):
                    dest_name = f"theme_{dest_name}"
                shutil.copy2(file_path, board_dest / dest_name)

        # board_sync_manifest.json 복사 또는 기본 데이터 생성 (파싱 오류 방지)
        orig_manifest = Path(__file__).parent.parent / "data" / "board" / "board_sync_manifest.json"
        board_dest = temp_dir / "board"
        board_dest.mkdir(parents=True, exist_ok=True)
        if orig_manifest.exists():
            shutil.copy2(orig_manifest, board_dest / "board_sync_manifest.json")
        else:
            (board_dest / "board_sync_manifest.json").write_text(
                '{"last_updated": "", "boards": {}, "new_listings": {}}', encoding="utf-8"
            )

        # statistics 데이터 복사
        # 1순위: 원래 data 디렉토리의 statistics (있다면) 전체 복사
        orig_stats = Path(__file__).parent.parent / "data" / "statistics"
        if orig_stats.exists():
            shutil.copytree(orig_stats, temp_dir / "statistics", dirs_exist_ok=True)
        else:
            # 2순위: fixtures 내부에서 복사 시도
            if (fixtures_dir / "statistics").exists():
                shutil.copytree(fixtures_dir / "statistics", temp_dir / "statistics", dirs_exist_ok=True)

        # heatmap 데이터 복사
        orig_heatmap = Path(__file__).parent.parent / "data" / "heatmap"
        if orig_heatmap.exists():
            shutil.copytree(orig_heatmap, temp_dir / "heatmap", dirs_exist_ok=True)
            
        # 재무제표 excel 파일 복사
        # 1순위: 원래 data 디렉토리의 파일 (있다면)
        orig_financial = Path(__file__).parent.parent / "data" / "financial_statements"
        if orig_financial.exists():
            shutil.copytree(orig_financial, temp_dir / "financial_statements", dirs_exist_ok=True)
        else:
            # 2순위: fixtures 내부에서 복사 시도
            financial_src = fixtures_dir / "statistics" / "financial_statements"
            if financial_src.exists():
                shutil.copytree(financial_src, temp_dir / "financial_statements", dirs_exist_ok=True)

    # 4. 의존성 컨테이너 재조립 (새로운 임시 DATA_DIR 반영)
    # 백그라운드 스레드 기동을 패치하여 테스트 프로세스에서의 리소스 충돌(RuntimeError)을 방지합니다.
    from unittest.mock import patch
    from synapstock.infrastructure.container import Container
    
    with patch.object(Container, "sync_financial_statements_from_drive", return_value=None), \
         patch.object(Container, "sync_boards_from_drive_in_background", return_value=None), \
         patch.object(Container, "sync_stock_splits_from_drive_in_background", return_value=None):
        container.__init__()

    # 4-2. dependencies 및 각 라우터 모듈 내의 전역 싱글톤 변수들을 새로운 컨테이너 인스턴스로 교체
    # 파이썬의 'from import' 바인딩 복사 특성을 우회하기 위해 이미 로드된 모든 라우터 모듈의 레퍼런스를 갱신합니다.
    import sys
    modules_to_patch = [
        "synapstock.presentation.web.core.dependencies",
        "synapstock.presentation.web.routes.board_routes",
        "synapstock.presentation.web.routes.stock_routes",
        "synapstock.presentation.web.routes.financial_routes",
        "synapstock.presentation.web.routes.report_routes",
        "synapstock.presentation.web.routes.statistics_routes",
        "synapstock.presentation.web.routes.heatmap_routes",
    ]
    for mod_name in modules_to_patch:
        if mod_name in sys.modules:
            mod = sys.modules[mod_name]
            if hasattr(mod, "query_service"):
                mod.query_service = container.query_service
            if hasattr(mod, "command_service"):
                mod.command_service = container.command_service
            if hasattr(mod, "media_service"):
                mod.media_service = container.media_service
            if hasattr(mod, "sync_service"):
                mod.sync_service = container.sync_service
            if hasattr(mod, "report_service"):
                mod.report_service = container.report_service
            if hasattr(mod, "drive_adapter"):
                mod.drive_adapter = container.drive_adapter
            if hasattr(mod, "news_scraper_adapter"):
                mod.news_scraper_adapter = container.news_scraper
            if hasattr(mod, "news_service"):
                mod.news_service = container.news_service
            if hasattr(mod, "statistics_service"):
                mod.statistics_service = container.statistics_service
            if hasattr(mod, "financial_service"):
                mod.financial_service = container.financial_service
            if hasattr(mod, "weekly_change_service"):
                mod.weekly_change_service = container.weekly_change_service
            if hasattr(mod, "board_file_sync_service"):
                mod.board_file_sync_service = container.board_file_sync_service
            if hasattr(mod, "stock_split_repo"):
                mod.stock_split_repo = container._stock_split_repo
            if hasattr(mod, "stock_split_sync_service"):
                mod.stock_split_sync_service = container._stock_split_sync_service

    yield temp_dir

    # 5. 환경 변수 복구
    if old_data_dir is not None:
        os.environ["DATA_DIR"] = old_data_dir
    else:
        os.environ.pop("DATA_DIR", None)

    for var, val in old_google_env.items():
        if val is not None:
            os.environ[var] = val
        else:
            os.environ.pop(var, None)

    # 6. 임시 디렉터리 삭제
    shutil.rmtree(temp_dir, ignore_errors=True)
    
    # 7. 컨테이너 원상 복구 (백그라운드 스레드는 패치하여 초기화)
    with patch.object(Container, "sync_financial_statements_from_drive", return_value=None), \
         patch.object(Container, "sync_boards_from_drive_in_background", return_value=None), \
         patch.object(Container, "sync_stock_splits_from_drive_in_background", return_value=None):
        container.__init__()

    # 7-2. 컨테이너 원상 복구 후 모듈 레퍼런스 복구
    for mod_name in modules_to_patch:
        if mod_name in sys.modules:
            mod = sys.modules[mod_name]
            if hasattr(mod, "query_service"):
                mod.query_service = container.query_service
            if hasattr(mod, "command_service"):
                mod.command_service = container.command_service
            if hasattr(mod, "media_service"):
                mod.media_service = container.media_service
            if hasattr(mod, "sync_service"):
                mod.sync_service = container.sync_service
            if hasattr(mod, "report_service"):
                mod.report_service = container.report_service
            if hasattr(mod, "drive_adapter"):
                mod.drive_adapter = container.drive_adapter
            if hasattr(mod, "news_scraper_adapter"):
                mod.news_scraper_adapter = container.news_scraper
            if hasattr(mod, "news_service"):
                mod.news_service = container.news_service
            if hasattr(mod, "statistics_service"):
                mod.statistics_service = container.statistics_service
            if hasattr(mod, "financial_service"):
                mod.financial_service = container.financial_service
            if hasattr(mod, "weekly_change_service"):
                mod.weekly_change_service = container.weekly_change_service
            if hasattr(mod, "board_file_sync_service"):
                mod.board_file_sync_service = container.board_file_sync_service
            if hasattr(mod, "stock_split_repo"):
                mod.stock_split_repo = container._stock_split_repo
            if hasattr(mod, "stock_split_sync_service"):
                mod.stock_split_sync_service = container._stock_split_sync_service

