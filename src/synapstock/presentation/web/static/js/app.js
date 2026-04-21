/**
 * @fileoverview SynapStock 프론트엔드 진입점.
 * @module app
 */
import { addLogEntry, initTabs, switchTab, initHistoryState } from './ui/tabs.js';
import { initTree, renderNode, updateStockCount, findStockByTicker, jumpToStock } from './ui/mindmap/tree.js';
import { 
    openModal, closeModal, showAddNodeModal, showAddStockModal, 
    deleteNode, deleteStock, initMindmapModals 
} from './ui/mindmap/modals.js';
import { initWebSocket } from './services/websocket.js';
import { initGlobalSearch, initSyncButton } from './ui/mindmap/actions.js';
import { 
    loadStockDashboard 
} from './ui/dashboard/manager.js';
import { initNewsEvents, triggerNewsAdd, fetchNews } from './ui/dashboard/news.js';
import { uploadReport, triggerReportUpload } from './ui/dashboard/reports.js';
import { initFinancialSidebar } from './ui/dashboard/financials.js';
import { statisticsView } from './ui/statistics/statistics_view.js';
import { statisticsMonthView } from './ui/statistics/statistics_month_view.js';
import { ceilingView } from './ui/statistics/ceiling_view.js';
import { capitalIncreaseView } from './ui/statistics/capital_increase_view.js';
import { bonusIssueView } from './ui/statistics/bonus_issue_view.js';

// ── 전역 상태 ─────────────────────────────────────────────────────────────
window._currentBoardData = null;
window._currentBoardName = '';
window._globalLocalReportCounts = {};
window._globalStockCache = [];
window._findStockByTicker = findStockByTicker;

/**
 * 전역 유틸리티 함수 노출 (HTML onclick 및 외부 연동 대응)
 */
window.openModal = openModal;
window.closeModal = closeModal;
window.showAddNodeModal = showAddNodeModal;
window.showAddStockModal = showAddStockModal;
window.triggerReportUpload = triggerReportUpload;
window.triggerNewsAdd = triggerNewsAdd;

/**
 * 종목 상세 페이지로 즉시 이동하는 전역 함수
 * @param {string} ticker - 종목 티커
 * @param {string} name - 종목명
 */
window._jumpToStock = (ticker, name) => {
    if (!ticker || ticker === 'none') return;
    
    // URL 상태 업데이트 (뒤로가기 지원)
    history.pushState({ tab: 'dashboard', ticker, name }, '', `/stock/${ticker}`);
    
    // 탭 전환 및 대시보드 로드
    switchTab('dashboard-tab', false);
    loadStockDashboard(ticker, name, loadBoardData, window._globalLocalReportCounts);
};

// 인자(loadBoardData) 주입이 필요한 함수 래핑
window.deleteNode = (nodeName) => deleteNode(nodeName, loadBoardData);
window.deleteStock = (ticker) => deleteStock(ticker, loadBoardData);

/**
 * 종목 기본 정보 조회 (통합용)
 */
async function fetchStockInfo(ticker) {
    try {
        const response = await fetch(`/api/stock/info/${ticker}`);
        if (response.ok) return await response.json();
    } catch (err) { console.error('Info API failed:', err); }
    return null;
}

/**
 * 보드 데이터 로드
 */
async function loadBoardData(name) {
    const treeContainer = document.getElementById('tree-container');
    treeContainer.innerHTML = '<div class="loading-shimmer">데이터를 불러오는 중...</div>';
    addLogEntry(`[API] 보드 데이터 요청: ${name}`, 'system');

    try {
        const response = await fetch(`/api/board?name=${name}`);
        if (!response.ok) throw new Error(`HTTP Error ${response.status}`);
        const data = await response.json();
        window._currentBoardData = data;

        // 리포트 수량 캐싱
        fetch('/api/reports/counts').then(res => res.json()).then(counts => {
            window._globalLocalReportCounts = counts;
            renderTree(data);
        }).catch(e => {
            console.error('Count API failed:', e);
            renderTree(data);
        });

    } catch (err) {
        addLogEntry(`[ERROR] '${name}' 로드 중 오류 발생: ${err.message}`, 'error');
        treeContainer.innerHTML = `<div style="color:#ef4444;padding:20px;text-align:center;">데이터 로드 실패: ${err.message}</div>`;
    }
}

function renderTree(data) {
    const treeContainer = document.getElementById('tree-container');
    treeContainer.innerHTML = '';
    const rootList = document.createElement('div');
    rootList.className = 'tree-root';
    renderNode(data, rootList, 0, window._globalLocalReportCounts, data, (t, n) => loadStockDashboard(t, n, loadBoardData, window._globalLocalReportCounts));
    treeContainer.appendChild(rootList);
    updateStockCount(data);
}

// ── DOMContentLoaded 진입점 ──────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initTree(loadBoardData);
    initWebSocket();
    initSyncButton();
    initHistoryState((t, n) => loadStockDashboard(t, n, loadBoardData, window._globalLocalReportCounts));
    initFinancialSidebar();
    initGlobalSearch((ticker, boardName, path) => jumpToStock(ticker, boardName, path, loadBoardData));
    initMindmapModals(loadBoardData);
    initNewsEvents(loadBoardData, fetchStockInfo, window._globalLocalReportCounts);

    // 파일 업로드 이벤트
    const input = document.getElementById('report-upload-input');
    if (input) {
        input.addEventListener('change', (e) => {
            const file = e.target.files[0];
            const ticker = window._currentUploadTicker; // From triggerReportUpload in reports.js
            if (file && ticker) {
                uploadReport(ticker, file, fetchStockInfo, loadBoardData, findStockByTicker);
            }
        });
    }

    // URL 라우팅 처리
    const path = window.location.pathname;
    if (path.startsWith('/stock/')) {
        const ticker = path.split('/').pop();
        if (ticker && ticker !== 'none') {
            switchTab('dashboard-tab', false);
            loadStockDashboard(ticker, null, loadBoardData, window._globalLocalReportCounts);
        }
    } else if (path.startsWith('/statistics')) {
        switchTab('statistics-tab', false);
        const statsContainer = document.getElementById('statistics-container');
        if (statsContainer) {
            if (path === '/statistics' || path.includes('netbuy') || path.includes('ranking')) {
                statisticsView.init(statsContainer);
            } else if (path.includes('month')) {
                statisticsMonthView.init(statsContainer);
            } else if (path.includes('ceiling')) {
                ceilingView.init(statsContainer);
            } else if (path.includes('capital-increase')) {
                capitalIncreaseView.render(statsContainer);
            } else if (path.includes('bonus-issue')) {
                bonusIssueView.render(statsContainer);
            }
        }
    }
});
