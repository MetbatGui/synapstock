"""WebSocket 연결 관리자 모듈.

실시간 로그 브로드캐스트를 위한 WebSocket 연결 풀을 관리합니다.
모듈 하단에 전역 싱글톤 인스턴스 ``manager`` 가 선언되어 있습니다.
"""

from fastapi import WebSocket


class ConnectionManager:
    """활성 WebSocket 연결을 관리하고 실시간 로그를 브로드캐스트하는 클래스.

    Attributes:
        active_connections (list[WebSocket]): 현재 연결된 WebSocket 객체 목록.
    """

    def __init__(self) -> None:
        """활성 연결 상태를 추적하기 위한 리스트를 초기화합니다."""
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        """새로운 WebSocket 연결을 승인하고 활성 목록에 추가합니다.

        Args:
            websocket (WebSocket): 추가할 FastAPI WebSocket 연결 객체.
        """
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """활성 연결 목록에서 특정 WebSocket 연결을 제거합니다.

        연결이 목록에 없는 경우 아무 작업도 수행하지 않습니다.

        Args:
            websocket (WebSocket): 제거할 FastAPI WebSocket 연결 객체.
        """
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str) -> None:
        """모든 활성 클라이언트에게 메시지를 전송합니다.

        전송에 실패한 연결(이미 끊어진 클라이언트)은 자동으로 목록에서 제거합니다.

        Args:
            message (str): 전송할 JSON 형태의 문자열 메시지.
        """
        bad_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                bad_connections.append(connection)

        # 유효하지 않은 연결 정리
        for bad in bad_connections:
            self.disconnect(bad)


# 전역 싱글톤 인스턴스
manager = ConnectionManager()
