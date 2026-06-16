import json
import shutil
from pathlib import Path
from datetime import datetime
import pytest
from synapstock.application.services.statistics_service import StatisticsService
from synapstock.domain.statistics.models import NewListing

@pytest.fixture
def temp_board_dir(tmp_path):
    """테스트를 위한 임시 보드 디렉토리 격리 제공 fixture"""
    board_dir = tmp_path / "board"
    board_dir.mkdir(parents=True, exist_ok=True)
    return board_dir

def test_ipo_sync_provisions_manifest_and_virtual_board(temp_board_dir):
    """3단계 복합 검증: IPO 데이터 유입 시 매니페스트 및 가상보드 PENDING 적재 무결성 검증"""
    
    # 0. 임시 파일 경로 세팅
    manifest_path = temp_board_dir / "board_sync_manifest.json"
    virtual_board_path = temp_board_dir / "virtual_신규상장주.json"
    
    # 1. 의존성 없이 StatisticsService 인스턴스 기동 (테스트 경로 명시적 주입)
    from synapstock.infrastructure.adapters.local.board_repo import LocalBoardSyncManifestRepository, LocalBoardRepository
    manifest_repository = LocalBoardSyncManifestRepository(manifest_path)
    board_repository = LocalBoardRepository(temp_board_dir)
    service = StatisticsService(
        manifest_repository=manifest_repository,
        board_repository=board_repository
    )

    
    # 2. 더미 신규상장주 데이터 목록 수립 (NewListing 도메인 모델 활용)
    dummy_listings = [
        NewListing(listing_date="2026-05-10", name="사이냅소프트", ticker="466410"),
        NewListing(listing_date="2026-05-08", name="뱅크웨어글로벌", ticker="199480"),
        NewListing(listing_date="2026-06-01", name="임의주식", ticker="none") # 티커가 none인 항목은 등록 배제 대상
    ]
    
    # 3. 최초 동기화 적재 실행
    service.sync_new_listings_to_virtual_board(dummy_listings)
    
    # --- 매니페스트(board_sync_manifest.json) 적재 검증 ---
    assert manifest_path.exists(), "통합 매니페스트 파일이 자동으로 디스크에 생성되어야 합니다."
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    
    assert "new_listings" in manifest_data
    # 유효한 티커만 매니페스트에 등록되었는지 검증
    assert "466410" in manifest_data["new_listings"]
    assert "199480" in manifest_data["new_listings"]
    assert "none" not in manifest_data["new_listings"] # none은 누락되어야 함
    
    # 개별 종목 속성 검증
    item_synap = manifest_data["new_listings"]["466410"]
    assert item_synap["name"] == "사이냅소프트"
    assert item_synap["status"] == "PENDING"
    assert item_synap["current_board"] == "virtual_신규상장주"
    assert len(item_synap["current_path"]) == 0
    
    # --- 가상보드(virtual_신규상장주.json) 적재 검증 ---
    assert virtual_board_path.exists(), "가상보드 파일이 자동으로 디스크에 생성되어야 합니다."
    virtual_board_data = json.loads(virtual_board_path.read_text(encoding="utf-8"))
    
    assert virtual_board_data["name"] == "신규상장주"
    stocks = virtual_board_data["nodes"]["신규상장주"]["stocks"]
    assert len(stocks) == 2 # 사이냅소프트, 뱅크웨어글로벌 2건
    
    assert any(s["name"] == "사이냅소프트" and s["ticker"] == "466410" for s in stocks)
    assert any(s["name"] == "뱅크웨어글로벌" and s["ticker"] == "199480" for s in stocks)
    
    # 4. 동일한 종목으로 2차 적재 시도 (Idempotency 멱등성 검증 - 중복 적재 예방)
    service.sync_new_listings_to_virtual_board(dummy_listings)
    
    # 다시 로드하여 갯수가 여전히 2개로 유지되는지 검사
    virtual_board_data_2 = json.loads(virtual_board_path.read_text(encoding="utf-8"))
    assert len(virtual_board_data_2["nodes"]["신규상장주"]["stocks"]) == 2, "동일 데이터 재동기화 시 가상보드 하위에 중복 적재가 차단되어야 합니다."


@pytest.mark.asyncio
async def test_stock_addition_automatically_assigns_pending_ipo(temp_board_dir):
    """보드에 종목 추가 시, 신규상장주(IPO) 대기 목록에 있던 녀석이면 상태를 ASSIGNED로 전이시키고 드라이브 동기화를 강제 실행합니다."""
    # 0. 임시 파일 경로 세팅
    manifest_path = temp_board_dir / "board_sync_manifest.json"
    virtual_board_path = temp_board_dir / "virtual_신규상장주.json"
    
    # 1. 초기 더미 매니페스트 생성 (990001 PENDING 상태)
    initial_manifest = {
        "last_updated": datetime.now().isoformat(),
        "boards": {
            "theme_IT": {
                "name": "IT",
                "last_modified": 1234567.0,
                "deleted": False
            },
            "virtual_신규상장주": {
                "name": "신규상장주",
                "last_modified": 1234567.0,
                "deleted": False
            }
        },
        "new_listings": {
            "990001": {
                "ticker": "990001",
                "name": "더미테크",
                "status": "PENDING",
                "updated_at": datetime.now().isoformat(),
                "current_board": "virtual_신규상장주",
                "current_path": []
            }
        }
    }
    manifest_path.write_text(json.dumps(initial_manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    
    # 2. 초기 가상보드 생성 (990001 포함)
    virtual_board = {
        "name": "신규상장주",
        "nodes": {
            "신규상장주": {
                "name": "신규상장주",
                "depth": 0,
                "parent_path": None,
                "stocks": [
                    {"name": "더미테크", "ticker": "990001", "aliases": [], "reports": [], "news": []}
                ]
            }
        }
    }
    virtual_board_path.write_text(json.dumps(virtual_board, indent=2, ensure_ascii=False), encoding="utf-8")
    
    # 3. 타겟 섹터 보드 생성 (theme_IT)
    theme_it_path = temp_board_dir / "theme_IT.json"
    theme_it = {
        "name": "IT",
        "nodes": {
            "IT": {
                "name": "IT",
                "depth": 0,
                "parent_path": None,
                "stocks": []
            },
            "IT/인터넷": {
                "name": "인터넷",
                "depth": 1,
                "parent_path": "IT",
                "stocks": []
            }
        }
    }
    theme_it_path.write_text(json.dumps(theme_it, indent=2, ensure_ascii=False), encoding="utf-8")
    
    # 4. 의존성 셋업
    from unittest.mock import AsyncMock, MagicMock
    from synapstock.application.services.board_file_sync_service import BoardFileSyncService
    from synapstock.application.services.command_service import BoardCommandService
    from synapstock.infrastructure.adapters.local.board_repo import LocalBoardRepository
    
    repo = LocalBoardRepository(root_dir=temp_board_dir)
    drive_adapter = MagicMock()
    drive_adapter.put_file = AsyncMock(return_value=True)
    drive_adapter.get_file = AsyncMock(return_value=None)
    
    from synapstock.infrastructure.adapters.local.board_repo import LocalBoardSyncManifestRepository
    manifest_repository = LocalBoardSyncManifestRepository(manifest_path)
    sync_service = BoardFileSyncService(
        repository=repo,
        drive_adapter=drive_adapter,
        theme_folder_id="dummy_folder",
        manifest_repository=manifest_repository
    )

    
    command_service = BoardCommandService(
        repository=repo,
        sync_service=sync_service
    )
    
    # 5. 종목 추가 수행 (비동기)
    success = await command_service.add_stock(
        board_name="theme_IT",
        parent_name="인터넷",
        stock_name="더미테크",
        ticker="990001"
    )
    
    assert success is True
    
    # --- 매니페스트 ASSIGNED 전환 검증 ---
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    item = manifest_data["new_listings"]["990001"]
    assert item["status"] == "ASSIGNED"
    assert item["current_board"] == "theme_IT"
    assert item["current_path"] == ["IT", "인터넷"]
    
    # --- 가상보드에서 해당 종목 자동 제거 검증 ---
    virtual_board_data = json.loads(virtual_board_path.read_text(encoding="utf-8"))
    stocks = virtual_board_data["nodes"]["신규상장주"].get("stocks", [])
    assert len(stocks) == 0, "가상보드 대기목록에서 자동 삭제되어야 합니다."
    
    # --- 구글 드라이브 sync_with_drive 트리거 검증 ---
    assert drive_adapter.put_file.call_count >= 1


@pytest.mark.asyncio
async def test_stock_deletion_from_ipo_board_turns_status_ignored(temp_board_dir):
    """엣지 케이스 1 검증: 가상보드(virtual_신규상장주)에서 종목 삭제 시 매니페스트 상태가 IGNORED가 되어 재유입을 방지해야 합니다."""
    # 0. 임시 파일 경로 세팅
    manifest_path = temp_board_dir / "board_sync_manifest.json"
    virtual_board_path = temp_board_dir / "virtual_신규상장주.json"
    
    # 1. 초기 더미 매니페스트 생성 (990003 PENDING 상태)
    initial_manifest = {
        "last_updated": datetime.now().isoformat(),
        "boards": {
            "virtual_신규상장주": {
                "name": "신규상장주",
                "last_modified": 1234567.0,
                "deleted": False
            }
        },
        "new_listings": {
            "990003": {
                "ticker": "990003",
                "name": "더미에너지",
                "status": "PENDING",
                "updated_at": datetime.now().isoformat(),
                "current_board": "virtual_신규상장주",
                "current_path": []
            }
        }
    }
    manifest_path.write_text(json.dumps(initial_manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    
    # 2. 초기 가상보드 생성 (990003 포함)
    virtual_board = {
        "name": "신규상장주",
        "nodes": {
            "신규상장주": {
                "name": "신규상장주",
                "depth": 0,
                "parent_path": None,
                "stocks": [
                    {"name": "더미에너지", "ticker": "990003", "aliases": [], "reports": [], "news": []}
                ]
            }
        }
    }
    virtual_board_path.write_text(json.dumps(virtual_board, indent=2, ensure_ascii=False), encoding="utf-8")
    
    # 3. 의존성 셋업
    from unittest.mock import AsyncMock, MagicMock
    from synapstock.application.services.board_file_sync_service import BoardFileSyncService
    from synapstock.application.services.command_service import BoardCommandService
    from synapstock.infrastructure.adapters.local.board_repo import LocalBoardRepository
    
    repo = LocalBoardRepository(root_dir=temp_board_dir)
    drive_adapter = MagicMock()
    drive_adapter.put_file = AsyncMock(return_value=True)
    drive_adapter.get_file = AsyncMock(return_value=None)
    
    from synapstock.infrastructure.adapters.local.board_repo import LocalBoardSyncManifestRepository
    manifest_repository = LocalBoardSyncManifestRepository(manifest_path)
    sync_service = BoardFileSyncService(
        repository=repo,
        drive_adapter=drive_adapter,
        theme_folder_id="dummy_folder",
        manifest_repository=manifest_repository
    )

    
    command_service = BoardCommandService(
        repository=repo,
        sync_service=sync_service
    )
    
    # 4. 가상보드에서 수동 삭제 호출
    success = await command_service.delete_stock("virtual_신규상장주", "990003")
    assert success is True
    
    # --- 매니페스트 상 상태가 IGNORED로 전환되었는지 검증 ---
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    item = manifest_data["new_listings"]["990003"]
    assert item["status"] == "IGNORED", "가상보드에서 직접 제거 시에는 무시(IGNORED) 상태로 락킹되어야 합니다."


@pytest.mark.asyncio
async def test_stock_deletion_from_sector_board_does_not_rollback_to_pending(temp_board_dir):
    """엣지 케이스 2 검증: 일반 섹터 보드에서 종목 삭제 시, 매니페스트 상 PENDING으로 복구되지 않고 ASSIGNED 상태가 유지되어야 합니다."""
    # 0. 임시 파일 경로 세팅
    manifest_path = temp_board_dir / "board_sync_manifest.json"
    
    # 1. 초기 더미 매니페스트 생성 (990004 ASSIGNED 상태)
    initial_manifest = {
        "last_updated": datetime.now().isoformat(),
        "boards": {
            "theme_IT": {
                "name": "IT",
                "last_modified": 1234567.0,
                "deleted": False
            }
        },
        "new_listings": {
            "990004": {
                "ticker": "990004",
                "name": "더미케미칼",
                "status": "ASSIGNED",
                "updated_at": datetime.now().isoformat(),
                "current_board": "theme_IT",
                "current_path": ["화학섹터"]
            }
        }
    }
    manifest_path.write_text(json.dumps(initial_manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    
    # 2. 초기 섹터 보드 생성 (theme_IT에 990004 포함)
    theme_it_path = temp_board_dir / "theme_IT.json"
    theme_it = {
        "name": "IT",
        "nodes": {
            "IT": {
                "name": "IT",
                "depth": 0,
                "parent_path": None,
                "stocks": []
            },
            "IT/화학섹터": {
                "name": "화학섹터",
                "depth": 1,
                "parent_path": "IT",
                "stocks": [
                    {"name": "더미케미칼", "ticker": "990004", "aliases": [], "reports": [], "news": []}
                ]
            }
        }
    }
    theme_it_path.write_text(json.dumps(theme_it, indent=2, ensure_ascii=False), encoding="utf-8")
    
    # 3. 의존성 셋업
    from unittest.mock import AsyncMock, MagicMock
    from synapstock.application.services.board_file_sync_service import BoardFileSyncService
    from synapstock.application.services.command_service import BoardCommandService
    from synapstock.infrastructure.adapters.local.board_repo import LocalBoardRepository
    
    repo = LocalBoardRepository(root_dir=temp_board_dir)
    drive_adapter = MagicMock()
    drive_adapter.put_file = AsyncMock(return_value=True)
    drive_adapter.get_file = AsyncMock(return_value=None)
    
    from synapstock.infrastructure.adapters.local.board_repo import LocalBoardSyncManifestRepository
    manifest_repository = LocalBoardSyncManifestRepository(manifest_path)
    sync_service = BoardFileSyncService(
        repository=repo,
        drive_adapter=drive_adapter,
        theme_folder_id="dummy_folder",
        manifest_repository=manifest_repository
    )

    
    command_service = BoardCommandService(
        repository=repo,
        sync_service=sync_service
    )
    
    # 4. 일반 테마보드에서 수동 삭제 호출
    success = await command_service.delete_stock("theme_IT", "990004")
    assert success is True
    
    # --- 매니페스트 상 상태가 복구(PENDING)되지 않고 ASSIGNED(혹은 이전 상태)로 고정되어 있는지 검증 ---
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    item = manifest_data["new_listings"]["990004"]
    assert item["status"] == "ASSIGNED", "일반 보드에서 삭제 시에는 PENDING으로 롤백되지 않고 ASSIGNED 상태가 유지되어야 합니다."


@pytest.mark.asyncio
async def test_stock_move_from_ipo_board_to_sector_board(temp_board_dir):
    """케이스 A 검증: 가상보드에서 삭제(delete_stock) 후 일반보드에 추가(add_stock)하는 '이동(Move)' 흐름 검증"""
    # 0. 임시 파일 경로 세팅
    manifest_path = temp_board_dir / "board_sync_manifest.json"
    virtual_board_path = temp_board_dir / "virtual_신규상장주.json"
    
    # 1. 초기 더미 매니페스트 생성 (990002 PENDING 상태)
    initial_manifest = {
        "last_updated": datetime.now().isoformat(),
        "boards": {
            "theme_IT": {
                "name": "IT",
                "last_modified": 1234567.0,
                "deleted": False
            },
            "virtual_신규상장주": {
                "name": "신규상장주",
                "last_modified": 1234567.0,
                "deleted": False
            }
        },
        "new_listings": {
            "990002": {
                "ticker": "990002",
                "name": "더미바이오",
                "status": "PENDING",
                "updated_at": datetime.now().isoformat(),
                "current_board": "virtual_신규상장주",
                "current_path": []
            }
        }
    }
    manifest_path.write_text(json.dumps(initial_manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    
    # 2. 초기 가상보드 생성 (990002 포함)
    virtual_board = {
        "name": "신규상장주",
        "nodes": {
            "신규상장주": {
                "name": "신규상장주",
                "depth": 0,
                "parent_path": None,
                "stocks": [
                    {"name": "더미바이오", "ticker": "990002", "aliases": [], "reports": [], "news": []}
                ]
            }
        }
    }
    virtual_board_path.write_text(json.dumps(virtual_board, indent=2, ensure_ascii=False), encoding="utf-8")
    
    # 3. 타겟 섹터 보드 생성 (theme_IT)
    theme_it_path = temp_board_dir / "theme_IT.json"
    theme_it = {
        "name": "IT",
        "nodes": {
            "IT": {
                "name": "IT",
                "depth": 0,
                "parent_path": None,
                "stocks": []
            },
            "IT/인터넷": {
                "name": "인터넷",
                "depth": 1,
                "parent_path": "IT",
                "stocks": []
            }
        }
    }
    theme_it_path.write_text(json.dumps(theme_it, indent=2, ensure_ascii=False), encoding="utf-8")
    
    # 4. 의존성 셋업
    from unittest.mock import AsyncMock, MagicMock
    from synapstock.application.services.board_file_sync_service import BoardFileSyncService
    from synapstock.application.services.command_service import BoardCommandService
    from synapstock.infrastructure.adapters.local.board_repo import LocalBoardRepository
    
    repo = LocalBoardRepository(root_dir=temp_board_dir)
    drive_adapter = MagicMock()
    drive_adapter.put_file = AsyncMock(return_value=True)
    drive_adapter.get_file = AsyncMock(return_value=None)
    
    from synapstock.infrastructure.adapters.local.board_repo import LocalBoardSyncManifestRepository
    manifest_repository = LocalBoardSyncManifestRepository(manifest_path)
    sync_service = BoardFileSyncService(
        repository=repo,
        drive_adapter=drive_adapter,
        theme_folder_id="dummy_folder",
        manifest_repository=manifest_repository
    )

    
    command_service = BoardCommandService(
        repository=repo,
        sync_service=sync_service
    )
    
    # 5. 이동 액션 실행
    # 5-1) 가상보드에서 삭제
    del_success = await command_service.delete_stock("virtual_신규상장주", "990002")
    assert del_success is True
    
    # 가상보드에서 삭제되었으므로, 매니페스트 상에서는 일시적으로 IGNORED 상태가 됨 (이동 중)
    manifest_data_1 = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest_data_1["new_listings"]["990002"]["status"] == "IGNORED"
    
    # 가상보드 파일 상에서도 제거 확인
    virtual_board_data_1 = json.loads(virtual_board_path.read_text(encoding="utf-8"))
    stocks_1 = virtual_board_data_1["nodes"]["신규상장주"].get("stocks", [])
    assert len(stocks_1) == 0
    
    # 5-2) 타겟 보드에 추가
    add_success = await command_service.add_stock(
        board_name="theme_IT",
        parent_name="인터넷",
        stock_name="더미바이오",
        ticker="990002"
    )
    assert add_success is True
    
    # --- 최종 검증: 매니페스트 상에서 ASSIGNED로 전환 ---
    manifest_data_2 = json.loads(manifest_path.read_text(encoding="utf-8"))
    item = manifest_data_2["new_listings"]["990002"]
    assert item["status"] == "ASSIGNED"
    assert item["current_board"] == "theme_IT"
    assert item["current_path"] == ["IT", "인터넷"]
    
    # --- 드라이브 싱크 호출 확인 ---
    assert drive_adapter.put_file.call_count >= 1


@pytest.mark.asyncio
async def test_stock_addition_outbox_flow(temp_board_dir):
    """Outbox와 Worker를 통해 종목 추가 비동기 이벤트가 구글 드라이브 동기화까지 전달되는지 전체 흐름 검증."""
    # 0. 파일 경로 세팅
    manifest_path = temp_board_dir / "board_sync_manifest.json"
    virtual_board_path = temp_board_dir / "virtual_신규상장주.json"
    
    # 1. 초기 매니페스트 및 가상 보드
    initial_manifest = {
        "last_updated": datetime.now().isoformat(),
        "boards": {
            "theme_IT": {"name": "IT", "last_modified": 1234567.0, "deleted": False},
            "virtual_신규상장주": {"name": "신규상장주", "last_modified": 1234567.0, "deleted": False}
        },
        "new_listings": {
            "990001": {
                "ticker": "990001",
                "name": "더미테크",
                "status": "PENDING",
                "updated_at": datetime.now().isoformat(),
                "current_board": "virtual_신규상장주",
                "current_path": []
            }
        }
    }
    manifest_path.write_text(json.dumps(initial_manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    
    # 2. 초기 가상보드 생성 (990001 포함)
    virtual_board = {
        "name": "신규상장주",
        "nodes": {
            "신규상장주": {
                "name": "신규상장주", "depth": 0, "parent_path": None,
                "stocks": [{"name": "더미테크", "ticker": "990001", "aliases": [], "reports": [], "news": []}]
            }
        }
    }
    virtual_board_path.write_text(json.dumps(virtual_board, indent=2, ensure_ascii=False), encoding="utf-8")
    
    # 3. 타겟 섹터 보드 생성 (theme_IT)
    theme_it_path = temp_board_dir / "theme_IT.json"
    theme_it = {
        "name": "IT",
        "nodes": {
            "IT": {"name": "IT", "depth": 0, "parent_path": None, "stocks": []},
            "IT/인터넷": {"name": "인터넷", "depth": 1, "parent_path": "IT", "stocks": []}
        }
    }
    theme_it_path.write_text(json.dumps(theme_it, indent=2, ensure_ascii=False), encoding="utf-8")
    
    # 4. 의존성 셋업 (아웃박스 및 워커 연동)
    from unittest.mock import AsyncMock, MagicMock
    from synapstock.infrastructure.adapters.events.in_memory_bus import InMemoryEventBusAdapter
    from synapstock.infrastructure.adapters.events.file_outbox import LocalFileEventOutboxAdapter
    from synapstock.application.events.worker import OutboxWorker
    from synapstock.application.services.board_file_sync_service import BoardFileSyncService
    from synapstock.application.services.command_service import BoardCommandService
    from synapstock.infrastructure.adapters.local.board_repo import LocalBoardRepository, LocalBoardSyncManifestRepository
    from synapstock.domain.events import StockAddedToBoard
    
    repo = LocalBoardRepository(root_dir=temp_board_dir)
    drive_adapter = MagicMock()
    drive_adapter.put_file = AsyncMock(return_value=True)
    drive_adapter.get_file = AsyncMock(return_value=None)
    
    manifest_repository = LocalBoardSyncManifestRepository(manifest_path)
    sync_service = BoardFileSyncService(
        repository=repo,
        drive_adapter=drive_adapter,
        theme_folder_id="dummy_folder",
        manifest_repository=manifest_repository
    )
    
    # 아웃박스 및 이벤트 버스 연동
    outbox_dir = temp_board_dir / "outbox"
    outbox_dir.mkdir(exist_ok=True)
    outbox = LocalFileEventOutboxAdapter(outbox_dir)
    event_bus = InMemoryEventBusAdapter(sync_mode=False)
    
    # 이벤트 발생 시 아웃박스 적재 구독
    event_bus.subscribe(StockAddedToBoard, lambda ev: outbox.save(ev))
    
    async def handle_stock_added(ev: StockAddedToBoard):
        sync_service.update_local_manifest(ev.board_id, deleted=False)
        await sync_service.handle_stock_addition_trigger(
            ev.ticker, ev.board_id, ev.parent_path.split("/")
        )
        await sync_service.sync_with_drive()
        
    worker_handlers = {
        "StockAddedToBoard": handle_stock_added,
    }
    worker = OutboxWorker(outbox=outbox, handlers=worker_handlers, base_delay=0.0)
    
    command_service = BoardCommandService(
        repository=repo,
        event_bus=event_bus
    )
    
    # 5. 종목 추가 수행 -> 이벤트가 발행되어 아웃박스에 적재됨
    success = await command_service.add_stock(
        board_name="theme_IT",
        parent_name="인터넷",
        stock_name="더미테크",
        ticker="990001"
    )
    assert success is True
    
    # 아웃박스 상태 조회: PENDING 상태로 1개 저장되어 있어야 함
    pending = outbox.load_pending()
    assert len(pending) == 1
    assert pending[0]["event"]["event_class"] == "StockAddedToBoard"
    
    # 아직 동기화가 실제로 일어나지 않았어야 함 (아웃박스에서 비동기 소모 대기 중)
    assert drive_adapter.put_file.call_count == 0
    
    # 6. 워커 구동 (수동으로 pending 이벤트 프로세스 1회 실행)
    await worker.process_pending_events()
    
    # 7. 소모 완료 후 검증
    # 매니페스트 ASSIGNED 전환 검증
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    item = manifest_data["new_listings"]["990001"]
    assert item["status"] == "ASSIGNED"
    
    # 가상보드에서 제거 검증
    virtual_board_data = json.loads(virtual_board_path.read_text(encoding="utf-8"))
    assert len(virtual_board_data["nodes"]["신규상장주"].get("stocks", [])) == 0
    
    # 구글 드라이브 sync_with_drive 트리거 검증
    assert drive_adapter.put_file.call_count >= 1
    
    # 아웃박스 상태 조회: 처리되었으므로 PENDING이 없어야 함
    assert len(outbox.load_pending()) == 0


@pytest.mark.asyncio
async def test_idempotent_event_consumption(temp_board_dir):
    """동일한 이벤트 ID를 가진 이벤트가 중복 유입되어도 멱등성이 보장되는지 검증."""
    # 0. 파일 경로 세팅
    manifest_path = temp_board_dir / "board_sync_manifest.json"
    
    # 1. 초기 매니페스트 생성 (processed_event_ids 필드가 복원 가능하도록 준비)
    initial_manifest = {
        "last_updated": datetime.now().isoformat(),
        "boards": {
            "theme_IT": {"name": "IT", "last_modified": 1234567.0, "deleted": False}
        },
        "new_listings": {},
        "processed_event_ids": []
    }
    manifest_path.write_text(json.dumps(initial_manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    
    # 2. 타겟 섹터 보드 생성
    theme_it_path = temp_board_dir / "theme_IT.json"
    theme_it = {
        "name": "IT",
        "nodes": {
            "IT": {"name": "IT", "depth": 0, "parent_path": None, "stocks": []},
            "IT/인터넷": {"name": "인터넷", "depth": 1, "parent_path": "IT", "stocks": []}
        }
    }
    theme_it_path.write_text(json.dumps(theme_it, indent=2, ensure_ascii=False), encoding="utf-8")
    
    # 3. 의존성 셋업
    from unittest.mock import AsyncMock, MagicMock
    from synapstock.infrastructure.adapters.events.in_memory_bus import InMemoryEventBusAdapter
    from synapstock.infrastructure.adapters.events.file_outbox import LocalFileEventOutboxAdapter
    from synapstock.application.events.worker import OutboxWorker
    from synapstock.application.services.board_file_sync_service import BoardFileSyncService
    from synapstock.application.services.command_service import BoardCommandService
    from synapstock.infrastructure.adapters.local.board_repo import LocalBoardRepository, LocalBoardSyncManifestRepository
    from synapstock.domain.events import StockAddedToBoard
    
    repo = LocalBoardRepository(root_dir=temp_board_dir)
    drive_adapter = MagicMock()
    drive_adapter.put_file = AsyncMock(return_value=True)
    drive_adapter.get_file = AsyncMock(return_value=None)
    
    manifest_repository = LocalBoardSyncManifestRepository(manifest_path)
    sync_service = BoardFileSyncService(
        repository=repo,
        drive_adapter=drive_adapter,
        theme_folder_id="dummy_folder",
        manifest_repository=manifest_repository
    )
    
    outbox_dir = temp_board_dir / "outbox"
    outbox_dir.mkdir(exist_ok=True)
    outbox = LocalFileEventOutboxAdapter(outbox_dir)
    
    # 멱등성 검증이 탑재된 이벤트 핸들러 정의
    async def handle_stock_added(ev: StockAddedToBoard):
        manifest = sync_service.load_local_manifest()
        if hasattr(manifest, "is_event_processed") and manifest.is_event_processed(ev.event_id):
            return  # 중복 스킵
            
        sync_service.update_local_manifest(ev.board_id, deleted=False)
        await sync_service.handle_stock_addition_trigger(
            ev.ticker, ev.board_id, ev.parent_path.split("/")
        )
        await sync_service.sync_with_drive()
        
        # 다시 불러와서 마킹하고 저장
        manifest = sync_service.load_local_manifest()
        if hasattr(manifest, "mark_event_processed"):
            manifest.mark_event_processed(ev.event_id)
            sync_service.save_local_manifest(manifest)
            
    worker_handlers = {
        "StockAddedToBoard": handle_stock_added,
    }
    worker = OutboxWorker(outbox=outbox, handlers=worker_handlers, base_delay=0.0)
    
    # 4. 첫 번째 이벤트 발생 및 처리
    event1 = StockAddedToBoard(
        board_id="theme_IT",
        parent_path="theme_IT/인터넷",
        ticker="035420",
        stock_name="NAVER"
    )
    
    # 아웃박스에 저장
    outbox_id1 = outbox.save(event1)
    
    # 1차 워커 소모 실행
    await worker.process_pending_events()
    
    # 1차 동기화 호출 확인
    first_put_count = drive_adapter.put_file.call_count
    assert first_put_count >= 1
    
    # 매니페스트에 이벤트 ID가 등록되었는지 검증
    manifest = sync_service.load_local_manifest()
    assert hasattr(manifest, "processed_event_ids")
    assert event1.event_id in manifest.processed_event_ids
    
    # 5. 동일한 이벤트를 아웃박스에 PENDING 상태로 강제 재적재 (중복 유입 가정)
    # event_id가 동일한 복제본
    event2 = StockAddedToBoard(
        board_id="theme_IT",
        parent_path="theme_IT/인터넷",
        ticker="035420",
        stock_name="NAVER"
    )
    # UUID 덮어쓰기
    object.__setattr__(event2, "event_id", event1.event_id)
    
    outbox_id2 = outbox.save(event2)
    assert outbox_id2 == event1.event_id # 아웃박스 파일명도 동일해짐
    
    # 2차 워커 소모 실행
    await worker.process_pending_events()
    
    # 6. 최종 검증: 2차 실행 시에는 멱등 필터링에 걸려 구글 드라이브 동기화 API가 중복 실행되지 않아야 함
    # (put_file 호출 횟수가 늘어나지 않고 1차 때와 동일하게 유지되어야 함)
    assert drive_adapter.put_file.call_count == first_put_count
