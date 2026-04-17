/**
 * 월간 통계 뷰(Monthly Statistics View) UI 모듈.
 * 월간 누적 수급 순위표 및 필터 렌더링을 담당합니다.
 */
import { statisticsService } from '../../services/statistics_service.js';

/**
 * 뷰 구동에 필요한 설정 상수 객체
 * @type {Object}
 */
const CONFIG = {
    SELECTORS: {
        MONTH_PICKER: 'stats-month-picker',
        REFRESH_BTN: 'stats-month-refresh',
        TABLE_CONTAINER: 'stats-month-table-container'
    }
};

/**
 * 월간 통계 뷰 모듈.
 * @namespace
 */
export const statisticsMonthView = {
    /** @type {string} */
    containerId: 'statistics-view',
    
    /**
     * 월간 통계 탭을 초기화하고 기본 레이아웃을 렌더링합니다.
     * @param {HTMLElement} container - 뷰가 렌더링될 DOM 컨테이너 (app.js에서 주입)
     * @returns {Promise<void>}
     */
    async init(container) {
        this.container = container;
        this.renderLayout();
        await this.loadInitialData();
    },

    /**
     * 월 선택 필터와 테이블 결과 영역을 포함한 레이아웃을 생성합니다.
     * @returns {void}
     */
    renderLayout() {
        // 현재 년-월 (YYYY-MM) 기본값 설정
        const now = new Date();
        const year = now.getFullYear();
        const month = String(now.getMonth() + 1).padStart(2, '0');
        const defaultMonth = `${year}-${month}`;

        this.container.innerHTML = `
            <div class="stats-container animate-fade-in">
                <div class="stats-header">
                    <h2><i class="fas fa-calendar-alt"></i> 월간 누적 수급 순위 (TOP 30)</h2>
                    <div class="stats-filters">
                        <input type="month" id="${CONFIG.SELECTORS.MONTH_PICKER}" class="stats-select" value="${defaultMonth}">
                        <button id="${CONFIG.SELECTORS.REFRESH_BTN}" class="stats-btn-refresh"><i class="fas fa-sync-alt"></i></button>
                    </div>
                </div>
                <div id="${CONFIG.SELECTORS.TABLE_CONTAINER}" class="stats-table-wrapper">
                    <div class="stats-loader">데이터를 불러오는 중...</div>
                </div>
            </div>
        `;

        this.attachEvents();
    },

    /**
     * 필터 변경 및 새로고침 이벤트 리스너를 바인딩합니다.
     * @private
     * @returns {void}
     */
    attachEvents() {
        const monthPicker = document.getElementById(CONFIG.SELECTORS.MONTH_PICKER);
        const refreshBtn = document.getElementById(CONFIG.SELECTORS.REFRESH_BTN);

        monthPicker.addEventListener('change', () => this.loadData());
        refreshBtn.addEventListener('click', () => this.loadData());
    },

    /**
     * 초기 데이터 로드
     * @async
     * @returns {Promise<void>}
     */
    async loadInitialData() {
        await this.loadData();
    },

    /**
     * 선택된 월에 따라 집계 데이터를 로드하고 화면을 갱신합니다.
     * @async
     * @returns {Promise<void>}
     */
    async loadData() {
        const tableWrapper = document.getElementById(CONFIG.SELECTORS.TABLE_CONTAINER);
        const month = document.getElementById(CONFIG.SELECTORS.MONTH_PICKER).value;

        if (!month) {
            tableWrapper.innerHTML = '<div class="stats-empty">대상 월을 선택해 주세요.</div>';
            return;
        }

        tableWrapper.innerHTML = '<div class="stats-loader"><i class="fas fa-spinner fa-spin"></i> 누적 데이터 계산 중...</div>';

        try {
            const summaryData = await statisticsService.getMonthlySummary(month);
            this.renderSummaryGrid(summaryData);
        } catch (error) {
            tableWrapper.innerHTML = `<div class="stats-error">오류 발생: ${error.message}</div>`;
        }
    },

    /**
     * 수급 데이터를 바탕으로 월간 랭킹 그리드를 렌더링합니다.
     * @param {Object} data - API 응답 데이터 (KOSPI/KOSDAQ 주체별 월간 랭킹)
     * @returns {void}
     */
    renderSummaryGrid(data) {
        const container = document.getElementById(CONFIG.SELECTORS.TABLE_CONTAINER);
        if (!data || !data.KOSPI || !data.KOSDAQ) {
            container.innerHTML = '<div class="stats-empty">표시할 데이터가 없습니다.</div>';
            return;
        }

        /**
         * 개별 월간 통계 테이블을 HTML로 변환합니다.
         * @param {string} title - 섹션 제목 (예: '외국인 (누적)')
         * @param {Object} rankingData - 랭킹 정보
         * @returns {string} Table HTML
         */
        const renderSubTable = (title, rankingData) => {
            if (!rankingData || !rankingData.items || rankingData.items.length === 0) {
                return `
                    <div class="stats-grid-item">
                        <h3 class="stats-grid-item-title">${title}</h3>
                        <div style="text-align:center;padding:20px;color:#6b7280;">해당 월 데이터 없음</div>
                    </div>
                `;
            }
            
            let html = `
                <div class="stats-grid-item">
                    <h3 class="stats-grid-item-title">${title}</h3>
                    <table class="stats-table">
                        <thead>
                            <tr>
                                <th class="col-rank">순위</th>
                                <th class="col-name">종목명</th>
                                <th class="col-amount">누적 순매수(백만)</th>
                            </tr>
                        </thead>
                        <tbody>
            `;

            rankingData.items.forEach(item => {
                html += `
                    <tr>
                        <td class="col-rank">${item.rank}</td>
                        <td class="col-name">
                            <div class="name-badge-wrapper">
                                <span class="stock-name-text stock-link" data-name="${item.name}" data-ticker="${item.ticker || ''}"><strong>${item.name}</strong></span>
                                <div class="badge-container"></div>
                            </div>
                        </td>
                        <td class="col-amount" style="font-weight:700; color:var(--text-primary);">${item.amount.toLocaleString()}</td>
                    </tr>
                `;
            });

            html += `</tbody></table></div>`;
            return html;
        };

        const gridHtml = `
            <div class="stats-markets-grid">
                ${renderSubTable('<i class="fas fa-university"></i> KOSPI <span>외국인(누적)</span>', data.KOSPI.FOREIGN)}
                ${renderSubTable('<i class="fas fa-university"></i> KOSPI <span>기관(누적)</span>', data.KOSPI.INSTITUTION)}
                ${renderSubTable('<i class="fas fa-microchip"></i> KOSDAQ <span>외국인(누적)</span>', data.KOSDAQ.FOREIGN)}
                ${renderSubTable('<i class="fas fa-microchip"></i> KOSDAQ <span>기관(누적)</span>', data.KOSDAQ.INSTITUTION)}
            </div>
        `;
        
        container.innerHTML = gridHtml;
        this.bindTableEvents(container);
    },

    /**
     * 렌더링된 요소에 대한 인터랙션(종목 클릭 리다이렉션)을 바인딩합니다.
     * @param {HTMLElement} container 
     * @private
     * @returns {void}
     */
    bindTableEvents(container) {
        container.querySelectorAll('.stock-link').forEach(el => {
            el.addEventListener('click', async (e) => {
                const stockName = e.currentTarget.dataset.name;
                const ticker = e.currentTarget.dataset.ticker;
                const originalContent = e.currentTarget.innerHTML;
                
                // 1. 이미 티커 정보가 있는 경우 (백엔드 최적화로 제공됨)
                if (ticker) {
                    window.location.href = `/stock/${ticker}`;
                    return;
                }

                // 2. 티커가 없는 경우에만 검색 API 호출
                try {
                    e.currentTarget.innerHTML = `<span style="opacity:0.6;">⏳ 검색중...</span>`;
                    const res = await fetch(`/api/stock/search?q=${encodeURIComponent(stockName)}`);
                    if (!res.ok) throw new Error('API Error');
                    const searchResults = await res.json();
                    
                    if (searchResults && searchResults.length > 0) {
                        const ticker = searchResults[0].ticker;
                        window.location.href = `/stock/${ticker}`;
                    } else {
                        alert(`종목 [${stockName}]의 정보를 시스템에서 찾을 수 없습니다.`);
                        e.currentTarget.innerHTML = originalContent;
                    }
                } catch(err) {
                    console.error('Ticker search failed:', err);
                    alert('종목 정보를 검색하는 도중 오류가 발생했습니다.');
                    e.currentTarget.innerHTML = originalContent;
                }
            });
        });
    }
};
