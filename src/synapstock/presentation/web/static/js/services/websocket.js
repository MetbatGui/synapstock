/**
 * @fileoverview 실시간 로그 WebSocket 통신 초기화 모듈.
 * @module services/websocket
 */
import { addLogEntry } from '../ui/tabs.js';

/**
 * 서버와 WebSocket 연결을 수립하고 실시간 로그 및 동기화 진행률을 수신합니다.
 *
 * `/ws/logs` 엔드포인트에 연결하며, 수신 메시지의 `type === 'log'`인 경우
 * 로그 콘솔에 출력하고 프로그레스 바를 업데이트합니다.
 * HTTPS 환경에서는 자동으로 `wss://` 프로토콜을 사용합니다.
 *
 * @returns {void}
 */
export function initWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const socket = new WebSocket(`${protocol}//${window.location.host}/ws/logs`);
    const progressBar = document.getElementById('sync-progress-bar');
    const statusIndicator = document.getElementById('sync-status-indicator');

    socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'log') {
            const isSuccess = data.message.includes('완료') || data.message.includes('성공');
            addLogEntry(data.message, isSuccess ? 'success' : 'info');

            progressBar.style.width = `${data.progress * 100}%`;

            if (data.progress >= 1.0) {
                statusIndicator.innerText = '● System Ready';
                statusIndicator.style.color = '#4ade80';
            } else {
                statusIndicator.innerText = '● Synchronizing...';
                statusIndicator.style.color = '#facc15';
            }
        }
    };

    socket.onopen = () => addLogEntry('[SYSTEM] 실시간 로그 서버에 연결되었습니다.', 'success');
}
