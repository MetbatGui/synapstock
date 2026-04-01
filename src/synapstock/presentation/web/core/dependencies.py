"""전역 서비스 싱글톤 및 Google Drive 리포트 인덱스 동기화 모듈.

서버 시작 시 ``BoardService`` 인스턴스를 생성하고, 선택적으로
``GoogleDriveAdapter`` 를 초기화합니다. 모듈 레벨에 제공되는
``service``와 ``drive_adapter`` 싱글톤은 모든 라우터에서 공유합니다.
"""
import os
import asyncio
import time
from pathlib import Path
from dotenv import load_dotenv

from synapstock.services.board_service import BoardService
from synapstock.adapters.local.board_repo import LocalBoardRepository
from synapstock.adapters.miro.miro_mindmap import MiroMindmapAdapter
from synapstock.adapters.disclosure.disclosure_adapter import DartDisclosureAdapter
from synapstock.adapters.financial.excel_adapter import ExcelFinancialDataAdapter
from synapstock.adapters.google.google_drive_adapter import GoogleDriveAdapter
from synapstock.adapters.scraper.httpx_scraper import HttpxNewsScraperAdapter

load_dotenv()

# ── 전역 서비스 레이어 싱글톤 ──────────────────────────────────────────────
repo = LocalBoardRepository(Path("data") / "board")
miro_adapter = MiroMindmapAdapter(os.getenv("MIRO_ACCESS_TOKEN", ""))
disclosure_adapter = DartDisclosureAdapter()
financial_adapter = ExcelFinancialDataAdapter(
    Path("data") / "financial_statements" / "financial_data.xlsx"
)
service = BoardService(repo, miro_adapter, disclosure_adapter, financial_adapter)

# ── 뉴스 스크래퍼 어댑터 (신규) ──────────────────────────────────────────
news_scraper_adapter = HttpxNewsScraperAdapter()

# ── Google Drive 어댑터 (온디맨드 다운로드용) ──────────────────────────────
drive_adapter = None
try:
    token_path = "secrets/token.json"
    root_id = os.getenv("GOOGLE_DRIVE_ROOT_FOLDER_ID")
    if os.path.exists(token_path) and root_id:
        drive_adapter = GoogleDriveAdapter(
            token_file=token_path,
            root_folder_id=root_id,
            client_secret_file="secrets/client_secret.json",
        )
except Exception as e:
    print(f"[ERROR] GoogleDriveAdapter 초기화 실패: {e}")

# ── 인덱스 동기화 상태 ──────────────────────────────────────────────────────
_last_index_sync_time = 0
_sync_lock = asyncio.Lock()


async def sync_indices_if_needed(force: bool = False):
    """필요한 경우(또는 강제로) 리포트 인덱스를 Google Drive와 동기화합니다.

    Args:
        force (bool): ``True``일 경우 5분 경과 여부와 상관없이 즉시 동기화를 수행합니다.
            기본값은 ``False``.

    Returns:
        None: 이 함수는 반환값이 없습니다.

    Note:
        - 마지막 동기화 시점으로부터 300초(5분)가 경과했을 때만 작동합니다.
        - ``list.json``과 ``reports.json`` 중 하나라도 누락되면 동기화를 시도합니다.
        - ``_sync_lock``을 통해 한 번에 하나의 프로세스만 동기화를 수행하도록 보장합니다 (Double-checked locking 패턴).
    """
    global _last_index_sync_time

    current_time = time.time()

    paths_exist = (
        Path("data/report/list.json").exists()
        and Path("data/report/reports.json").exists()
    )
    if not force and paths_exist and (current_time - _last_index_sync_time) < 300:
        return

    async with _sync_lock:
        # 락 획득 후 다시 한 번 시간 체크 (Double-checked locking 패턴)
        if not force and (time.time() - _last_index_sync_time) < 300:
            return

        try:
            if drive_adapter:
                print("[SYSTEM] 인덱스 동기화 시작...")
                # 1. list.json 동기화
                list_data = drive_adapter.get_file("list.json")
                if list_data:
                    with open("data/report/list.json", "wb") as f:
                        f.write(list_data)

                # 2. reports.json 동기화
                reports_data = drive_adapter.get_file("reports.json")
                if reports_data:
                    with open("data/report/reports.json", "wb") as f:
                        f.write(reports_data)

                _last_index_sync_time = time.time()
                print(f"[SYSTEM] 인덱스 동기화 완료: {time.ctime(_last_index_sync_time)}")
        except Exception as e:
            print(f"[ERROR] 인덱스 동기화 실패: {e}")
