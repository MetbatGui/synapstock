from unittest.mock import AsyncMock, patch
import pytest
from fastapi.testclient import TestClient

from evenezer.presentation.web.server import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.mark.asyncio
async def test_internal_news_added_notification_flows(client):
    """POST /api/internal/news-added 호출 시 드라이브 동기화를 수행하고 WebSocket 브로드캐스트를 전송해야 한다."""
    
    # 1. 의존성 및 매니저 모킹
    # server lifespan 또는 container의 news_service 모킹
    from evenezer.infrastructure.container import container
    
    # news_service.sync_from_drive()가 즉시 호출되어야 함
    mock_sync = AsyncMock()
    container.news_service.sync_from_drive = mock_sync

    # Websocket manager broadcast 모킹
    with patch("evenezer.presentation.web.server.manager.broadcast", new_callable=AsyncMock) as mock_broadcast:
        # 2. API 호출
        payload = {
            "ticker": "005930",
            "title": "삼성전자 신규 기사",
            "url": "http://example.com/samsung-news",
            "date": "2026-07-08"
        }
        
        response = client.post("/api/internal/news-added", json=payload)
        
        # 3. 검증
        assert response.status_code == 200
        assert response.json() == {"status": "success"}

        # 드라이브 동기화가 감지하자마자 1회 비동기로 실행되었는지 검증
        mock_sync.assert_called_once()
        
        # WebSocket 브로드캐스트가 지정된 포맷으로 전송되었는지 검증
        mock_broadcast.assert_called_once()
        broadcast_data = mock_broadcast.call_args[0][0]
        import json
        data = json.loads(broadcast_data)
        assert data["type"] == "news_added"
        assert data["ticker"] == "005930"
        assert data["title"] == "삼성전자 신규 기사"
