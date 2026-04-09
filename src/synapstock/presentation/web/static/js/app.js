/**
 * @fileoverview SynapStock 프론트엔드 진입점.
 *
 * 전역 상태를 초기화하고, 각 UI/서비스 모듈을 조합하여 애플리케이션을 구동합니다.
 * HTML `onclick` 핸들러에서 접근할 수 있도록 필요한 함수를 `window`에 노출합니다.
 *
 * @module app
 */
import { addLogEntry, initTabs, switchTab, initHistoryState, initFinancialSidebar } from './ui/tabs.js';
import { initTree, renderNode, updateStockCount, findStockByTicker, jumpToStock } from './ui/tree.js';
import { openModal, closeModal, showAddNodeModal, showAddStockModal, triggerNewsAdd,
         triggerReportUpload, deleteNode, deleteStock, initSyncButton, initGlobalSearch, initModalEvents,
         CURRENT_UPLOAD_TICKER } from './ui/modals.js';
import { initWebSocket } from './services/websocket.js';
import { fetchReports, uploadReport } from './services/report_service.js';
import { fetchNews } from './services/news_service.js';
import { statisticsView } from './ui/statistics_view.js';

// ── 전역 상태 ─────────────────────────────────────────────────────────────
window._currentBoardData = null;
window._currentTicker = null;
window._currentBoardName = '';
window._globalLocalReportCounts = {};
window._globalStockCache = [];
window._findStockByTicker = findStockByTicker;

// ── 내부 헬퍼 ─────────────────────────────────────────────────────────────

/**
 * 티커 심볼로 종목 기본 정보(이름, 리포트 목록, 뉴스 목록)를 서버에서 조회합니다.
 *
 * @param {string} ticker - 조회할 종목 티커 심볼.
 * @returns {Promise<{ticker: string, name: string|null, reports: string[], news: Object[]}|null>}
 *     종목 정보 객체. 조회 실패 시 `null`.
 */
async function fetchStockInfo(ticker) {
    try {
        const response = await fetch(`/api/stock/info/${ticker}`);
        if (response.ok) return await response.json();
    } catch (err) {
        console.error('Failed to fetch stock info:', err);
    }
    return null;
}

/**
 * 특정 종목의 DART 공시 목록을 조회하여 `#disclosure-list` 요소에 렌더링합니다.
 *
 * @param {string} ticker - 조회할 종목 티커 심볼.
 * @returns {Promise<void>}
 */
async function fetchDisclosures(ticker) {
    const listEl = document.getElementById('disclosure-list');
    if (!listEl) return;
    try {
        const response = await fetch(`/api/disclosure/${ticker}`);
        const data = await response.json();
        if (!data || !Array.isArray(data) || data.length === 0) {
            listEl.innerHTML = '<div style="text-align:center;color:#6b7280;padding:20px;">최근 1년 이내 공시가 없습니다.</div>';
            return;
        }
        listEl.innerHTML = '';
        data.forEach(item => {
            const entry = document.createElement('div');
            entry.className = 'disclosure-item';
            entry.innerHTML = `
                <a href="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${item.rcpNo}"
                   target="_blank" class="disclosure-title" title="${item.title}"
                   style="color:#e5e7eb !important;text-decoration:none !important;font-size:0.95rem !important;display:block !important;">${item.title}</a>
                <span class="disclosure-date" style="color:#9ca3af !important;font-size:0.85rem !important;">${item.date}</span>
            `;
            listEl.appendChild(entry);
        });
    } catch (err) {
        listEl.innerHTML = `<div style="text-align:center;color:#ef4444;padding:20px;">로드 실패: ${err.message}</div>`;
    }
}

/**
 * 특정 기업의 분기별 재무(매출) 데이터를 조회하여 사이드바에 렌더링합니다.
 *
 * @param {string} name - 조회할 기업명.
 * @returns {Promise<void>}
 */
async function fetchFinancials(name) {
    const listEl = document.getElementById('financial-list-sidebar');
    if (!listEl) return;
    try {
        const response = await fetch(`/api/stock/financials?name=${encodeURIComponent(name)}`);
        const data = await response.json();
        if (!data || !Array.isArray(data) || data.length === 0) {
            listEl.innerHTML = '<div style="text-align:center;color:#6b7280;padding:40px;">데이터가 없습니다.</div>';
            return;
        }
        listEl.innerHTML = '';
        data.forEach(item => {
            const entry = document.createElement('div');
            entry.style.cssText = 'display:flex;justify-content:space-between;padding:12px 0;border-bottom:1px solid rgba(255,255,255,0.05);';
            entry.innerHTML = `
                <span style="color:#9ca3af;font-weight:500;">${item.quarter}</span>
                <span style="color:#e5e7eb;font-weight:600;">${item.value.toLocaleString()}</span>
            `;
            listEl.appendChild(entry);
        });
    } catch (err) {
        listEl.innerHTML = `<div style="text-align:center;color:#ef4444;padding:20px;">로드 실패: ${err.message}</div>`;
    }
}

/**
 * 지정된 보드의 계층형 데이터를 서버에서 가져와 트리를 렌더링합니다.
 *
 * 로드 성공 시 `window._currentBoardData`와 `window._globalLocalReportCounts`를 갱신합니다.
 *
 * @param {string} name - 로드할 보드 파일명.
 * @returns {Promise<void>}
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

        try {
            const countsResponse = await fetch('/api/reports/counts');
            window._globalLocalReportCounts = await countsResponse.json();
        } catch (e) {
            console.error('Failed to fetch report counts:', e);
        }

        treeContainer.innerHTML = '';
        const rootList = document.createElement('div');
        rootList.className = 'tree-root';
        renderNode(data, rootList, 0, window._globalLocalReportCounts, data, loadStockDashboard);
        treeContainer.appendChild(rootList);

        updateStockCount(data);
        addLogEntry(`[API] '${name}' 보드 데이터를 성공적으로 로드했습니다.`, 'success');
    } catch (err) {
        addLogEntry(`[ERROR] '${name}' 로드 중 오류 발생: ${err.message}`, 'error');
        treeContainer.innerHTML = `<div style="color:#ef4444;padding:20px;text-align:center;">데이터 로드 실패: ${err.message}</div>`;
    }
}

/**
 * 특정 종목의 상세 대시보드(차트, 리포트, 뉴스, 공시)를 렌더링합니다.
 *
 * `ticker`가 없거나 `'none'`이면 플레이스홀더를 표시합니다.
 * `name`이 없으면 `fetchStockInfo`를 통해 종목명을 비동기로 보완합니다.
 *
 * @param {string} ticker - 대시보드를 표시할 종목 티커 심볼.
 * @param {string=} name - 종목명. 없으면 서버에서 자동 조회. 기본값은 `null`.
 * @returns {void}
 */
function loadStockDashboard(ticker, name = null) {
    const container = document.getElementById('dashboard-container');
    const placeholder = document.getElementById('dashboard-placeholder');

    if (!ticker || ticker === 'none') {
        placeholder.style.display = 'flex';
        container.style.display = 'none';
        return;
    }

    if (!name) {
        fetchStockInfo(ticker).then(info => {
            if (info && info.name) {
                const titleEl = document.querySelector('.dashboard-header h1');
                if (titleEl) titleEl.innerText = `${info.name} (${ticker})`;
                addLogEntry(`[UI] 종목명 확인: ${info.name}`, 'success');
            }
        });
    }

    const displayTitle = name ? `${name} (${ticker})` : ticker;
    placeholder.style.display = 'none';
    container.style.display = 'block';
    addLogEntry(`[UI] 종목 상세 조회: ${displayTitle}`, 'info');

    container.innerHTML = `
        <div class="card dashboard-card" style="padding:25px;max-width:1400px;margin:0 auto;">
            <div class="dashboard-header" style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid rgba(255,255,255,0.1);padding-bottom:25px;">
                <div>
                    <h1 style="font-size:2.8rem;font-weight:700;background:linear-gradient(90deg,#00d2ff,#9d50bb);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin:0;">${displayTitle}</h1>
                    <p style="color:#9ca3af;margin:8px 0 0 0;font-size:1rem;">Data Source: Naver Finance & DART</p>
                </div>
                <div style="text-align:right">
                    <span class="ticker-badge" style="background:rgba(0,210,255,0.1);border:1px solid #00d2ff;padding:8px 20px;border-radius:20px;color:#00d2ff;font-weight:700;font-size:1.1rem;">${ticker}</span>
                </div>
            </div>
            <div class="dashboard-body" style="display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1fr) minmax(0,1.2fr);gap:25px;margin-top:25px;">
                <div class="left-column">
                    <div class="chart-section" style="background:rgba(0,0,0,0.2);border-radius:24px;padding:25px;text-align:center;">
                        <h3 style="margin-top:0;margin-bottom:15px;font-size:1.2rem;color:#e5e7eb;font-weight:600;">실시간 차트</h3>
                        <img src="https://ssl.pstatic.net/imgfinance/chart/item/area/day/${ticker}.png?v=${Date.now()}"
                             style="width:100%;max-width:800px;border-radius:16px;filter:invert(0.9) hue-rotate(180deg) brightness(1.1);margin-bottom:20px;transition:transform 0.3s;cursor:zoom-in;"
                             onmouseover="this.style.transform='scale(1.02)'" onmouseout="this.style.transform='scale(1)'">
                        <div class="button-group" style="display:flex;justify-content:center;gap:15px;">
                            <a href="https://finance.naver.com/item/main.naver?code=${ticker}" target="_blank" class="btn btn-naver" style="background:#03c75a;color:white;border:none;padding:12px 30px;border-radius:10px;font-weight:700;text-decoration:none;display:inline-flex;align-items:center;gap:8px;font-size:1rem;">
                                <i class="fas fa-external-link-alt"></i> 네이버 증권 홈
                            </a>
                        </div>
                    </div>
                    <div class="report-section card" style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.05);padding:25px;border-radius:20px;margin-top:25px;">
                        <h3 style="margin-top:0;margin-bottom:20px;font-size:1.3rem;color:#ef4444 !important;display:flex;align-items:center;justify-content:space-between;gap:10px;font-weight:700;">
                            <div style="display:flex;align-items:center;gap:10px;"><span>📊</span> 리포트 (PDF)</div>
                            <button class="btn btn-secondary btn-sm" onclick="triggerReportUpload('${ticker}')" style="background:rgba(239,68,68,0.1);border:1px solid #ef4444;color:#ef4444;padding:4px 12px;font-size:0.85rem;">추가</button>
                        </h3>
                        <div id="report-list" class="report-list">
                            <div class="loading-mini" style="text-align:center;color:#9ca3af;padding:10px;">리포트 정보를 가져오는 중...</div>
                        </div>
                    </div>
                </div>
                <div class="middle-column">
                    <div class="news-section card" style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.05);padding:25px;border-radius:20px;height:100%;display:flex;flex-direction:column;">
                        <h3 style="margin-top:0;margin-bottom:20px;font-size:1.3rem;color:#facc15 !important;display:flex;align-items:center;justify-content:space-between;gap:10px;font-weight:700;">
                            <div style="display:flex;align-items:center;gap:10px;"><span>📰</span> 주요 뉴스</div>
                            <button class="btn btn-secondary btn-sm" onclick="triggerNewsAdd('${ticker}','${name || ticker}')" style="background:rgba(250,204,21,0.1);border:1px solid #facc15;color:#facc15;padding:4px 12px;font-size:0.85rem;">추가</button>
                        </h3>
                        <div id="news-list" class="news-list" style="flex:1;">
                            <div class="loading-mini" style="text-align:center;color:#9ca3af;padding:10px;">뉴스 정보를 가져오는 중...</div>
                        </div>
                    </div>
                </div>
                <div class="right-column" style="display:flex;flex-direction:column;gap:20px;height:100%;">
                    <div class="disclosure-section card" style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.05);padding:25px;border-radius:20px;display:flex;flex-direction:column;flex:1;">
                        <h3 style="margin-top:0;margin-bottom:20px;font-size:1.3rem;color:#00d2ff !important;display:flex;align-items:center;gap:10px;font-weight:700;">
                            <span>📋</span> 최근 DART 공시
                        </h3>
                        <div id="disclosure-list" class="disclosure-list" style="overflow-y:auto !important;flex:1 !important;">
                            <div class="loading-mini" style="text-align:center;color:#9ca3af;padding:30px;">공시 정보를 가져오는 중...</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;

    fetchDisclosures(ticker);
    fetchReports(ticker, name, fetchStockInfo, loadBoardData);
    fetchNews(ticker, fetchStockInfo, loadBoardData, window._globalLocalReportCounts);

    if (name) {
        fetchFinancials(name);
    } else {
        fetchStockInfo(ticker).then(info => {
            if (info && info.name) fetchFinancials(info.name);
        });
    }
}

/**
 * HTML `onclick` 속성에서 호출할 수 있도록 함수를 전역 스코프에 노출합니다.
 *
 * ES Module 스코프는 전역이 아니므로, 인라인 핸들러에서 접근하려면
 * 명시적으로 `window`에 등록해야 합니다.
 *
 * @namespace window
 * @property {Function} closeModal
 * @property {Function} openModal
 * @property {Function} showAddNodeModal
 * @property {Function} showAddStockModal
 * @property {Function} triggerReportUpload
 * @property {Function} triggerNewsAdd
 * @property {Function} deleteStock
 * @property {Function} deleteNode
 */
window.closeModal = closeModal;
window.openModal = openModal;
window.showAddNodeModal = showAddNodeModal;
window.showAddStockModal = showAddStockModal;
window.triggerReportUpload = triggerReportUpload;
window.triggerNewsAdd = triggerNewsAdd;
window.deleteStock = (ticker) => deleteStock(ticker, loadBoardData);
window.deleteNode = (nodeName) => deleteNode(nodeName, loadBoardData);

// ── DOMContentLoaded 진입점 ──────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initTree(loadBoardData);
    initWebSocket();
    initSyncButton();
    initHistoryState(loadStockDashboard);
    initFinancialSidebar();
    initGlobalSearch((ticker, boardName, path) => jumpToStock(ticker, boardName, path, loadBoardData));
    initModalEvents(loadBoardData, fetchNews, fetchStockInfo, window._globalLocalReportCounts);

    // 파일 업로드 이벤트
    const input = document.getElementById('report-upload-input');
    if (input) {
        input.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (file && window._currentUploadTicker) {
                uploadReport(window._currentUploadTicker, file, fetchStockInfo, loadBoardData, findStockByTicker);
            }
        });
    }

    // URL 기반 초기 상태 설정
    const path = window.location.pathname;
    if (path.startsWith('/stock/')) {
        const parts = path.split('/');
        const ticker = parts[parts.length - 1];
        if (ticker && ticker !== 'none') {
            switchTab('dashboard-tab', false);
            loadStockDashboard(ticker);
        }
    } else if (path.startsWith('/statistics')) {
        switchTab('statistics-tab', false);
        
        // 서브 네비게이션 액티브 갱신 및 SPA 라우팅 바인딩
        document.querySelectorAll('.stats-nav-item').forEach(item => {
            const route = item.dataset.route;
            // 활성화 처리
            if ((path === '/statistics' && route === 'netbuy-ranking') || path.includes(route)) {
                item.classList.add('active');
            } else {
                item.classList.remove('active');
            }
            // Link Navigation
            item.addEventListener('click', (e) => {
                e.preventDefault();
                window.location.href = item.href; 
            });
        });

        // 서브 뷰 동적 렌더링
        const statsContainer = document.getElementById('statistics-container');
        if (statsContainer) {
            if (path === '/statistics' || path.includes('netbuy') || path.includes('ranking')) {
                statisticsView.init(statsContainer);
            } else if (path.includes('raw')) {
                statsContainer.innerHTML = '<div class="stats-empty"><h2>일별 RAW 데이터</h2><p style="margin-top:20px; color:#9ca3af;">화면은 현재 준비 중입니다.</p></div>';
            } else if (path.includes('month')) {
                statsContainer.innerHTML = '<div class="stats-empty"><h2>월별 누적 순매수도</h2><p style="margin-top:20px; color:#9ca3af;">화면은 현재 준비 중입니다.</p></div>';
            } else {
                statsContainer.innerHTML = '<div class="stats-empty">존재하지 않는 페이지입니다.</div>';
            }
        }
    }
});

// triggerReportUpload 에서 window._currentUploadTicker 를 업데이트하도록 재정의
window.triggerReportUpload = (ticker) => {
    window._currentUploadTicker = ticker;
    const uploadInput = document.getElementById('report-upload-input');
    if (uploadInput) {
        uploadInput.value = '';
        uploadInput.click();
    }
};
