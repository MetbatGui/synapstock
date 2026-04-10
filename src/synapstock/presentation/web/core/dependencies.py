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

from synapstock.infrastructure.container import container

# 전역 서비스 및 유즈케이스 싱글톤 (컨테이너로부터 획득)
query_service = container.query_service
command_service = container.command_service
media_service = container.media_service
sync_service = container.sync_service
report_service = container.report_service
drive_adapter = container.drive_adapter
news_scraper_adapter = container.news_scraper
statistics_service = container.statistics_service

async def sync_indices_if_needed(force: bool = False):
    """(하위 호환성 유지) ReportService를 통해 동기화를 수행합니다."""
    if report_service:
        if force:
            report_service.sync_index()
        else:
            # ReportService 내부의 get_reports_by_stock 등이 자동 동기화를 관리함
            pass
