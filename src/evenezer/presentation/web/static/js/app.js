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
import { initFinancialSidebar } from './ui/dashboard/financials.js?v=1.8';
import { statisticsView } from './ui/statistics/statistics_view.js';
import { statisticsMonthView } from './ui/statistics/statistics_month_view.js';
import { ceilingView } from './ui/statistics/ceiling_view.js';
import { consecutiveGrowthView } from './ui/statistics/consecutive_growth_view.js';
import { capitalIncreaseView } from './ui/statistics/capital_increase_view.js';
import { bonusIssueView } from './ui/statistics/bonus_issue_view.js';
import { convertibleBondView } from './ui/statistics/convertible_bond_view.js';
import { bondWithWarrantsView } from './ui/statistics/bond_with_warrants_view.js';
import { newListingView } from './ui/statistics/new_listing_view.js';
import { financialAnalysisView } from './ui/statistics/financial_analysis_view.js';
import { weeklyChangeView } from './ui/statistics/weekly_change_view.js';
import { stockSplitView } from './ui/statistics/stock_split_view.js';
import { heatmapView } from './ui/statistics/heatmap_view.js';

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

// 통계 뷰 객체 전역 노출 (인라인 이벤트 핸들러 대응)
// window.capitalIncreaseView = capitalIncreaseView;
window.bonusIssueView = bonusIssueView;
window.stockSplitView = stockSplitView;
// window.convertibleBondView = convertibleBondView;
// window.bondWithWarrantsView = bondWithWarrantsView;

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

/**
 * 특정 보드로 즉시 점프하여 마인드맵을 로드하고 탭을 전환하는 전역 함수
 * @param {string} boardName - 보드 파일명 (theme_IT 등)
 */
window._jumpToBoard = (boardName) => {
    if (!boardName) return;
    
    // URL 상태 업데이트 (뒤로가기 지원)
    history.pushState({ tab: 'mindmap' }, '', '/');
    
    // 탭 전환
    switchTab('mindmap-tab', false);
    
    // 보드 드롭다운 변경 및 보드 로드 트리거
    const select = document.getElementById('board-select');
    if (select) {
        select.value = boardName;
        // 체인지 이벤트 트리거
        select.dispatchEvent(new Event('change'));
    } else {
        // 셀렉트 박스가 없는 경우 수동 데이터 로드
        loadBoardData(boardName);
    }
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
    renderNode(data, rootList, 0, window._globalLocalReportCounts, data, (t, n) => loadStockDashboard(t, n, loadBoardData, window._globalLocalReportCounts), loadBoardData);
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
    initGlobalSearch((ticker, boardName, path, name) => {
        if (window._jumpToStock) {
            window._jumpToStock(ticker, name || '');
        }
    });
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
            // } else if (path.includes('capital-increase')) {
            //     capitalIncreaseView.render(statsContainer);
            } else if (path.includes('bonus-issue')) {
                bonusIssueView.render(statsContainer);
            // } else if (path.includes('convertible-bond')) {
            //     convertibleBondView.render(statsContainer);
            // } else if (path.includes('bond-with-warrants')) {
            //     bondWithWarrantsView.render(statsContainer);
            } else if (path.includes('new-listing')) {
                newListingView.render(statsContainer);
            } else if (path.includes('stock-split')) {
                stockSplitView.render(statsContainer);
            } else if (path.includes('heatmap')) {
                heatmapView.init(statsContainer);
            } else if (path.includes('financial')) {
                financialAnalysisView.init(statsContainer);
            } else if (path.includes('weekly-change')) {
                weeklyChangeView.init(statsContainer);
            }
        }
    } else if (path === '/heatmap') {
        switchTab('heatmap-tab', false);
        const heatmapContainer = document.getElementById('heatmap-tab-container');
        if (heatmapContainer) heatmapView.init(heatmapContainer);
    }
    
    // 최상위 탭 전환 시 히트맵 동적 렌더링 연동
    document.querySelectorAll('.nav-links .nav-item').forEach(item => {
        item.addEventListener('click', () => {
            const targetTab = item.getAttribute('data-tab');
            if (targetTab === 'heatmap-tab') {
                const container = document.getElementById('heatmap-tab-container');
                if (container) heatmapView.init(container);
            }
        });
    });

    // 통계 서브 내비게이션 이벤트 (SPA 처리)
    const statsSubNav = document.querySelector('.stats-subnav');
    if (statsSubNav) {
        statsSubNav.addEventListener('click', (e) => {
            const link = e.target.closest('.stats-nav-item');
            if (!link) return;

            e.preventDefault();
            const href = link.getAttribute('href');
            const route = link.getAttribute('data-route');

            // URL 업데이트
            history.pushState({ tab: 'statistics', route }, '', href);

            // 모든 탭에서 active 제거 후 현재 탭에 추가
            document.querySelectorAll('.stats-nav-item').forEach(item => item.classList.remove('active'));
            link.classList.add('active');

            // 뷰 렌더링
            const statsContainer = document.getElementById('statistics-container');
            if (statsContainer) {
                if (route === 'netbuy-ranking' || href === '/statistics') {
                    statisticsView.init(statsContainer);
                } else if (route === 'month') {
                    statisticsMonthView.init(statsContainer);
                } else if (route === 'ceiling') {
                    ceilingView.init(statsContainer);
                // } else if (route === 'capital-increase') {
                //     capitalIncreaseView.render(statsContainer);
                } else if (route === 'bonus-issue') {
                    bonusIssueView.render(statsContainer);
                // } else if (route === 'convertible-bond') {
                //     convertibleBondView.render(statsContainer);
                // } else if (route === 'bond-with-warrants') {
                //     bondWithWarrantsView.render(statsContainer);
                } else if (route === 'new-listing') {
                    newListingView.render(statsContainer);
                } else if (route === 'stock-split') {
                    stockSplitView.render(statsContainer);
                } else if (route === 'heatmap') {
                    heatmapView.init(statsContainer);
                } else if (route === 'growth') {
                    consecutiveGrowthView.init(statsContainer);
                } else if (route === 'financial') {
                    financialAnalysisView.init(statsContainer);
                } else if (route === 'weekly-change') {
                    weeklyChangeView.init(statsContainer);
                }
            }
        });

        // 초기 진입 시 active 클래스 설정
        const currentPath = window.location.pathname;
        document.querySelectorAll('.stats-nav-item').forEach(link => {
            const href = link.getAttribute('href');
            if (currentPath === href || (currentPath === '/statistics' && href === '/statistics')) {
                link.classList.add('active');
            } else if (currentPath.startsWith(href) && href !== '/statistics') {
                link.classList.add('active');
            } else {
                link.classList.remove('active');
            }
        });
    }

    // popstate 이벤트에서 통계 탭 뒤로가기/앞으로가기 완벽 지원
    window.addEventListener('popstate', (event) => {
        const currentPath = window.location.pathname;
        if (currentPath.startsWith('/statistics')) {
            switchTab('statistics-tab', false);
            
            // 내비게이션 상태 업데이트
            document.querySelectorAll('.stats-nav-item').forEach(link => {
                const href = link.getAttribute('href');
                if (currentPath === href || (currentPath === '/statistics' && href === '/statistics')) {
                    link.classList.add('active');
                } else if (currentPath.startsWith(href) && href !== '/statistics') {
                    link.classList.add('active');
                } else {
                    link.classList.remove('active');
                }
            });

            // 뷰 렌더링
            const statsContainer = document.getElementById('statistics-container');
            if (statsContainer) {
                if (currentPath === '/statistics' || currentPath.includes('netbuy') || currentPath.includes('ranking')) {
                    statisticsView.init(statsContainer);
                } else if (currentPath.includes('month')) {
                    statisticsMonthView.init(statsContainer);
                } else if (currentPath.includes('ceiling')) {
                    ceilingView.init(statsContainer);
                // } else if (currentPath.includes('capital-increase')) {
                //     capitalIncreaseView.render(statsContainer);
                } else if (currentPath.includes('bonus-issue')) {
                    bonusIssueView.render(statsContainer);
                // } else if (currentPath.includes('convertible-bond')) {
                //     convertibleBondView.render(statsContainer);
                // } else if (currentPath.includes('bond-with-warrants')) {
                //     bondWithWarrantsView.render(statsContainer);
                } else if (currentPath.includes('new-listing')) {
                    newListingView.render(statsContainer);
                } else if (currentPath.includes('stock-split')) {
                    stockSplitView.render(statsContainer);
                } else if (currentPath.includes('heatmap')) {
                    heatmapView.init(statsContainer);
                } else if (currentPath.includes('financial')) {
                    financialAnalysisView.init(statsContainer);
                } else if (currentPath.includes('weekly-change')) {
                    weeklyChangeView.init(statsContainer);
                }
            }
        } else if (currentPath === '/heatmap') {
            switchTab('heatmap-tab', false);
            const heatmapContainer = document.getElementById('heatmap-tab-container');
            if (heatmapContainer) heatmapView.init(heatmapContainer);
        }
    });
});
