/**
 * @fileoverview 종목 상세 대시보드 메인 관리 모듈.
 * @module ui/dashboard/manager
 */
import { addLogEntry } from '../tabs.js';
import { fetchDisclosures } from './disclosure.js';
import { fetchReports } from './reports.js';
import { fetchNews } from './news.js';
import { fetchFinancials } from './financials.js?v=1.8';

/**
 * 티커 심볼로 종목 기본 정보(이름, 리포트 목록, 뉴스 목록)를 서버에서 조회합니다.
 * @param {string} ticker 
 * @returns {Promise<Object|null>}
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
 * 특정 종목의 상세 대시보드(차트, 리포트, 뉴스, 공시)를 렌더링합니다.
 *
 * @param {string} ticker - 종목 티커 심볼.
 * @param {string=} name - 종목명.
 * @param {function(): void} loadBoardData - 보드 데이터 갱신 함수.
 * @param {Object} globalLocalReportCounts - 로컬 리포트 카운트 객체.
 */
export function loadStockDashboard(ticker, name = null, loadBoardData, globalLocalReportCounts) {
    const container = document.getElementById('dashboard-container');
    const placeholder = document.getElementById('dashboard-placeholder');

    if (!ticker || ticker === 'none') {
        placeholder.style.display = 'flex';
        container.style.display = 'none';
        return;
    }

    // 서버 데이터로 보완
    fetchStockInfo(ticker).then(info => {
        if (info) {
            if (info.name) {
                const titleEl = document.querySelector('.dashboard-header h1');
                if (titleEl) titleEl.innerText = `${info.name} (${ticker})`;
            }
            const pathEl = document.querySelector('.dashboard-header p');
            if (pathEl && info.path && info.path.length > 0) {
                pathEl.innerText = info.path.join(' > ');
            }
            if (info.name) addLogEntry(`[UI] 종목 정보 동기화 완료: ${info.name}`, 'success');
        }
    });

    const displayTitle = name ? `${name} (${ticker})` : ticker;
    placeholder.style.display = 'none';
    container.style.display = 'block';
    addLogEntry(`[UI] 종목 상세 조회: ${displayTitle}`, 'info');

    container.innerHTML = `
        <div class="card dashboard-card">
            <div class="dashboard-header">
                <div>
                    <h1>${displayTitle}</h1>
                    <p>Loading path information...</p>
                </div>
                <div style="text-align:right">
                    <span class="ticker-badge">${ticker}</span>
                </div>
            </div>
            <div class="dashboard-body">
                <div class="left-column">
                    <div class="chart-section">
                        <h3>실시간 차트</h3>
                        <img src="https://ssl.pstatic.net/imgfinance/chart/item/area/day/${ticker}.png?v=${Date.now()}">
                        <div class="button-group">
                            <a href="https://finance.naver.com/item/main.naver?code=${ticker}" target="_blank" class="btn btn-naver">
                                <i class="fas fa-external-link-alt"></i> 네이버 증권 홈
                            </a>
                        </div>
                    </div>
                    <div class="report-section card">
                        <h3 style="display:flex; align-items:center; justify-content:space-between; color:#ef4444 !important;">
                            <div><span>📊</span> 리포트 (PDF)</div>
                            <button class="btn btn-secondary btn-sm" onclick="triggerReportUpload('${ticker}')">추가</button>
                        </h3>
                        <div id="report-list" class="report-list">
                            <div class="loading-mini">리포트 정보를 가져오는 중...</div>
                        </div>
                    </div>
                </div>
                <div class="middle-column">
                    <div class="news-section card">
                        <h3 style="display:flex; align-items:center; justify-content:space-between; color:#facc15 !important;">
                            <div><span>📰</span> 주요 뉴스</div>
                            <div style="display: flex; gap: 5px;">
                                <button class="btn btn-secondary btn-sm" onclick="if(window._refreshDashboardNews) window._refreshDashboardNews()"><i class="fas fa-sync-alt"></i> 새로고침</button>
                                <button class="btn btn-secondary btn-sm" onclick="triggerNewsAdd('${ticker}','${name || ticker}')">추가</button>
                            </div>
                        </h3>
                        <div id="news-list" class="news-list">
                            <div class="loading-mini">뉴스 정보를 가져오는 중...</div>
                        </div>
                    </div>
                </div>
                <div class="right-column">
                    <div class="disclosure-section card">
                        <h3 style="color:#00d2ff !important;"><span>📋</span> 최근 DART 공시</h3>
                        <div id="disclosure-list" class="disclosure-list">
                            <div class="loading-mini">공시 정보를 가져오는 중...</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;

    fetchDisclosures(ticker);
    fetchReports(ticker, name, fetchStockInfo, loadBoardData);
    fetchNews(ticker, fetchStockInfo, loadBoardData, globalLocalReportCounts);

    if (name) {
        fetchFinancials(name);
    } else {
        fetchStockInfo(ticker).then(info => {
            if (info && info.name) fetchFinancials(info.name);
        });
    }

    // 실시간 뉴스 갱신을 위한 전역 상태 및 헬퍼 바인딩
    window._currentDashboardTicker = ticker;
    window._refreshDashboardNews = () => {
        if (window._currentDashboardTicker === ticker) {
            fetchNews(ticker, fetchStockInfo, loadBoardData, globalLocalReportCounts);
        }
    };
}
