import json
import logging
from fastapi import APIRouter
from pydantic import BaseModel

from evenezer.infrastructure.container import container
from evenezer.presentation.web.core.websocket_manager import manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/internal", tags=["internal"])


class NewsAddedNotification(BaseModel):
    ticker: str | None = None
    title: str
    url: str
    date: str


@router.post("/news-added")
async def internal_news_added(payload: NewsAddedNotification):
    """외부(텔레그램 봇)로부터 뉴스가 추가되었다는 신호를 받으면,

    즉시 구글 드라이브 동기화를 수행하여 로컬 저장소를 최신화한 뒤
    웹소켓으로 브라우저 클라이언트들에 알림을 쏩니다.
    """
    logger.info(f"[InternalAPI] 뉴스 추가 알림 수신 - {payload.title} ({payload.ticker})")
    
    # 1. 즉시 구글 드라이브로부터 최신 데이터를 로컬로 땡겨옴
    try:
        await container.news_service.sync_from_drive()
        logger.info("[InternalAPI] 뉴스 알림 수신 후 동기화 완료")
    except Exception as e:
        logger.error(f"[InternalAPI] 뉴스 추가 후 즉각 동기화 중 오류 발생: {e}")
        # 오류가 나도 브로드캐스트는 보낼 수 있도록 계속 진행

    # 2. 웹소켓 브로드캐스트 전송
    await manager.broadcast(
        json.dumps({
            "type": "news_added",
            "ticker": payload.ticker,
            "title": payload.title,
            "url": payload.url,
            "date": payload.date
        }, ensure_ascii=False)
    )
    
    return {"status": "success"}
