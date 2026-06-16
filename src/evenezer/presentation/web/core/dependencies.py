"""전역 서비스 싱글톤 및 Google Drive 리포트 인덱스 동기화 모듈.

서버 시작 시 ``BoardService`` 인스턴스를 생성하고, 선택적으로
``GoogleDriveAdapter`` 를 초기화합니다. 모듈 레벨에 제공되는
``service``와 ``drive_adapter`` 싱글톤은 모든 라우터에서 공유합니다.
"""

import logging

logger = logging.getLogger(__name__)

from evenezer.infrastructure.container import container

# 전역 서비스 및 유즈케이스 싱글톤 (컨테이너로부터 획득)
query_service = container.query_service
command_service = container.command_service
media_service = container.media_service
sync_service = container.sync_service
report_service = container.report_service
drive_adapter = container.drive_adapter
news_scraper_adapter = container.news_scraper
news_service = container.news_service
statistics_service = container.statistics_service
financial_service = container.financial_service
weekly_change_service = container.weekly_change_service
board_file_sync_service = container.board_file_sync_service
stock_split_sync_service = container._stock_split_sync_service
stock_split_repo = container._stock_split_repo



async def sync_indices_if_needed(force: bool = False):
    """(하위 호환성 유지) ReportService를 통해 동기화를 수행합니다."""
    if report_service:
        if force:
            await report_service.sync_index()
        else:
            # ReportService 내부의 get_reports_by_stock 등이 자동 동기화를 관리함
            pass


async def sync_news_archive():
    """뉴스 아카이브를 구글 드라이브와 스마트 동기화합니다."""
    if news_service:
        await news_service.sync_from_drive()


async def sync_all_new_listings_if_needed():
    """서버 기동 시 또는 필요 시 신규상장주(2024~2026) 데이터를 구글 드라이브로부터 백그라운드 동기화합니다."""
    if statistics_service:
        try:
            logger.info("[Startup] 신규상장주(2024~2026) 백그라운드 동기화 시작")
            await statistics_service.sync_all_new_listings(force_sync=True)
            logger.info("[Startup] 신규상장주(2024~2026) 백그라운드 동기화 완료")
        except Exception as e:
            logger.error(f"[Startup] 신규상장주 백그라운드 동기화 중 오류: {e}")
