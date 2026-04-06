"""전역 서비스 싱글톤 및 Google Drive 리포트 인덱스 동기화 모듈.

서버 시작 시 ``BoardService`` 인스턴스를 생성하고, 선택적으로
``GoogleDriveAdapter`` 를 초기화합니다. 모듈 레벨에 제공되는
``service``와 ``drive_adapter`` 싱글톤은 모든 라우터에서 공유합니다.
"""
import os
import asyncio
import time
from pathlib import Path
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

from synapstock.services.board_service import BoardService
from synapstock.adapters.local.board_repo import LocalBoardRepository
from synapstock.adapters.miro.miro_mindmap import MiroMindmapAdapter
from synapstock.adapters.disclosure.disclosure_adapter import DartDisclosureAdapter
from synapstock.adapters.financial.excel_adapter import ExcelFinancialDataAdapter
from synapstock.adapters.google.google_drive_adapter import GoogleDriveAdapter
from synapstock.adapters.scraper.httpx_scraper import HttpxNewsScraperAdapter
from synapstock.adapters.scraper.naver_ticker_adapter import NaverTickerSearchAdapter
from synapstock.services.report_service import ReportService

load_dotenv()

# ── 전역 서비스 레이어 싱글톤 ──────────────────────────────────────────────
repo = LocalBoardRepository(Path("data") / "board")
miro_adapter = MiroMindmapAdapter(os.getenv("MIRO_ACCESS_TOKEN", ""))
disclosure_adapter = DartDisclosureAdapter()
financial_adapter = ExcelFinancialDataAdapter(
    Path("data") / "financial_statements" / "financial_data.xlsx"
)
ticker_search_adapter = NaverTickerSearchAdapter()
service = BoardService(repo, miro_adapter, ticker_search_adapter, disclosure_adapter, financial_adapter)

# ── 뉴스 스크래퍼 어댑터 (신규) ──────────────────────────────────────────
news_scraper_adapter = HttpxNewsScraperAdapter()

# ── Google Drive 어댑터 및 서비스 싱글톤 ──────────────────────────────────────
drive_adapter = None
report_service = None

# 폴더 ID 정의
REPORT_FOLDER_ID = os.getenv("GOOGLE_DRIVE_REPORT_FOLDER_ID")
SUPPLY_DEMAND_FOLDER_ID = os.getenv("GOOGLE_DRIVE_SUPPLY_DEMAND_FOLDER_ID")

try:
    token_path = "secrets/token.json"
    client_secret_path = "secrets/client_secret.json"

    # 폴더명을 키워드로 하는 맵 생성
    folders = {
        "report": REPORT_FOLDER_ID,
        "sd": SUPPLY_DEMAND_FOLDER_ID
    }

    # 범용 Google Drive 어댑터 생성
    if os.path.exists(token_path):
        drive_adapter = GoogleDriveAdapter(
            token_file=token_path,
            folders=folders,
            client_secret_file=client_secret_path,
        )

    # 3. 리포트 서비스 초기화
    if drive_adapter and REPORT_FOLDER_ID:
        report_service = ReportService(
            storage=drive_adapter,
            report_folder_id=REPORT_FOLDER_ID
        )
except Exception as e:
    logger.error(f"[ERROR] 서비스 초기화 실패: {e}")

async def sync_indices_if_needed(force: bool = False):
    """(하위 호환성 유지) ReportService를 통해 동기화를 수행합니다."""
    if report_service:
        if force:
            report_service.sync_index()
        else:
            # ReportService 내부의 get_reports_by_stock 등이 자동 동기화를 관리함
            pass
