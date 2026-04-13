import { statisticsService } from '../services/statistics_service.js';

/**
 * @typedef {Object} StreakConfig
 * @property {number} THRESHOLD_HOT - 'HOT' 테마가 적용되는 최소 연속 일수
 * @property {number} MIN_DISPLAY_DAYS - 배지를 표시할 최소 연속 일수 (초과 시 표시)
 */

/**
 * @typedef {Object} RankChangeConfig
 * @property {number} EXPLOSIVE_THRESHOLD - 폭발적 순위 변동 기준 (삼각형 크기 확대)
 */

/**
 * 뷰 구동에 필요한 설정 상수 객체
 * @type {Object}
 */
const CONFIG = {
    /** @type {StreakConfig} */
    STREAK: {
        THRESHOLD_HOT: 4,
        MIN_DISPLAY_DAYS: 1
    },
    /** @type {Object.<string, string>} */
    HIGH_PRICE_CLASSES: {
        '역·신': 'hp-red',
        '역·근': 'hp-orange',
        '52·신': 'hp-yellow',
        '52·근': 'hp-lightgreen'
    },
    /** @type {RankChangeConfig} */
    RANK_CHANGE: {
        EXPLOSIVE_THRESHOLD: 10
    }
};

/**
 * 통계 뷰(Statistics View) UI 모듈.
 * 수급 순위표 렌더링, 필터링, 동기화 및 종목 상세 리다이렉션을 담당합니다.
 * 
 * @namespace
 */
export const statisticsView = {
    /** @type {string} */
    containerId: 'statistics-view',
    
    /**
     * 통계 탭을 초기화하고 기본 레이아웃을 렌더링합니다.
     * @param {HTMLElement} container - 뷰가 렌더링될 DOM 컨테이너 (app.js에서 주입)
     * @returns {Promise<void>}
     */
    async init(container) {
        this.container = container;
        this.renderLayout();
        await this.loadInitialData();
    },

    /**
     * 필터바와 테이블 결과 영역을 포함한 기본 HTML 구조를 생성합니다.
     * @returns {void}
     */
    renderLayout() {
        this.container.innerHTML = `
            <div class="stats-container animate-fade-in">
                <div class="stats-header">
                    <h2><i class="fas fa-chart-line"></i> 일별 수급 종합 상황판</h2>
                    <div class="stats-filters">
                        <select id="stats-date" class="stats-select"></select>
                        <button id="stats-refresh" class="stats-btn-refresh"><i class="fas fa-sync-alt"></i></button>
                    </div>
                </div>
                <div id="stats-table-container" class="stats-table-wrapper">
                    <div class="stats-loader">데이터를 불러오는 중...</div>
                </div>
            </div>
        `;

        this.attachEvents();
    },

    /**
     * 날짜 선택 상자와 동기화 버튼에 대한 이벤트 리스너를 바인딩합니다.
     * @private
     * @returns {void}
     */
    attachEvents() {
        const dateSelect = document.getElementById('stats-date');
        const refreshBtn = document.getElementById('stats-refresh');

        dateSelect.addEventListener('change', () => this.loadData());
        refreshBtn.addEventListener('click', () => this.handleSync());
    },

    /**
     * 구글 드라이브와 수급 데이터를 동기화하고 화면을 최신 상태로 갱신합니다.
     * @async
     * @returns {Promise<void>}
     */
    async handleSync() {
        const refreshBtn = document.getElementById('stats-refresh');
        const icon = refreshBtn.querySelector('i');
        
        try {
            refreshBtn.disabled = true;
            icon.classList.add('fa-spin');
            
            const result = await statisticsService.syncStatistics();
            console.log('Sync result:', result);
            
            await this.updateDateList();
            await this.loadData();
        } catch (error) {
            console.error('Sync failed:', error);
            alert('동기화 실패: ' + error.message);
        } finally {
            refreshBtn.disabled = false;
            icon.classList.remove('fa-spin');
        }
    },

    /**
     * 컴포넌트 마운트 후 초기 데이터(날짜 목록 및 최신 데이터)를 로드합니다.
     * @async
     * @returns {Promise<void>}
     */
    async loadInitialData() {
        await this.updateDateList();
        await this.loadData();
    },

    /**
     * 서버에서 가용한 날짜 목록을 조회하여 <select> 요소를 업데이트합니다.
     * @async
     * @returns {Promise<void>}
     */
    async updateDateList() {
        const dates = await statisticsService.getAvailableDates('KOSPI', 'FOREIGN');
        
        const dateSelect = document.getElementById('stats-date');
        const currentVal = dateSelect.value;
        
        dateSelect.innerHTML = dates.map(d => `<option value="${d}">${d}</option>`).join('');
        
        if (dates.includes(currentVal)) {
            dateSelect.value = currentVal;
        } else if (dates.length > 0) {
            dateSelect.value = dates[0];
        }
    },

    /**
     * 현재 선택된 날짜의 수급 요약 정보를 API로부터 조회하여 화면에 그립니다.
     * @async
     * @returns {Promise<void>}
     */
    async loadData() {
        const tableWrapper = document.getElementById('stats-table-container');
        const date = document.getElementById('stats-date').value;

        if (!date) {
            tableWrapper.innerHTML = `
                <div class="stats-empty">
                    <div class="empty-content">
                        <i class="fas fa-folder-open"></i>
                        <p>가용한 수급 데이터가 없습니다.</p>
                        <button id="empty-sync-btn" class="stats-btn-sync">최신 데이터 가져오기</button>
                    </div>
                </div>
            `;
            
            const syncBtn = document.getElementById('empty-sync-btn');
            if (syncBtn) {
                syncBtn.addEventListener('click', () => this.handleSync());
            }
            return;
        }

        tableWrapper.innerHTML = '<div class="stats-loader"><i class="fas fa-spinner fa-spin"></i> 분석 중...</div>';

        try {
            const summaryData = await statisticsService.getDailySummary(date);
            this.renderSummaryGrid(summaryData);
        } catch (error) {
            tableWrapper.innerHTML = `<div class="stats-error">오류 발생: ${error.message}</div>`;
        }
    },

    /**
     * 수급 데이터를 바탕으로 코스피/코스닥 4분할 그리드 레이아웃을 렌더링합니다.
     * @param {Object} data - API 응답 데이터 (KOSPI/KOSDAQ 주체별 랭킹 객체)
     * @returns {void}
     */
    renderSummaryGrid(data) {
        const container = document.getElementById('stats-table-container');
        if (!data || !data.KOSPI || !data.KOSDAQ) {
            container.innerHTML = '<div class="stats-empty">표시할 데이터가 없습니다.</div>';
            return;
        }

        /**
         * 외인/기관 공통 매수 종목(쌍끌이) 여부를 판단하기 위한 집합을 반환합니다.
         * @param {Object} catF - 외국인 랭킹 정보
         * @param {Object} catI - 기관 랭킹 정보
         * @returns {Set<string>} 쌍끌이 종목명 Set
         */
        const getIntersection = (catF, catI) => {
            const setF = new Set(catF?.items?.map(i => i.name) || []);
            const setI = new Set(catI?.items?.map(i => i.name) || []);
            return new Set([...setF].filter(x => setI.has(x)));
        };

        const kospiDouble = getIntersection(data.KOSPI.FOREIGN, data.KOSPI.INSTITUTION);
        const kosdaqDouble = getIntersection(data.KOSDAQ.FOREIGN, data.KOSDAQ.INSTITUTION);

        /**
         * 개별 수급 상세 테이블을 HTML로 변환합니다.
         * @param {string} title - 섹션 제목 (예: '외국인')
         * @param {Object} rankingData - 랭킹 정보 (items 포함)
         * @param {Set<string>} doubleSet - 쌍끌이 종목 Set
         * @returns {string} 생성된 Table HTML
         */
        const renderSubTable = (title, rankingData, doubleSet) => {
            if (!rankingData || !rankingData.items) return `<div>데이터 없음</div>`;
            
            let html = `
                <div class="stats-grid-item">
                    <h3 class="stats-section-title">${title}</h3>
                    <table class="stats-table">
                        <thead>
                            <tr>
                                <th class="col-rank">순위</th>
                                <th class="col-change">변동</th>
                                <th class="col-name">종목명</th>
                                <th class="col-amount">순매수금액(백만)</th>
                                <th class="col-highprice">신고가</th>
                            </tr>
                        </thead>
                        <tbody>
            `;

            rankingData.items.forEach(item => {
                const changeHtml = this.getChangeIndicator(item);
                
                // 연속 매수 배지 스타일 결정
                let consecutiveClass = 'badge-mini badge-consecutive';
                if (item.consecutive_days >= CONFIG.STREAK.THRESHOLD_HOT) {
                    consecutiveClass += ' badge-consecutive-hot';
                }
                
                const consecutiveHtml = item.consecutive_days > CONFIG.STREAK.MIN_DISPLAY_DAYS 
                    ? `<span class="${consecutiveClass}">🔥 ${item.consecutive_days}</span>`
                    : '';

                const doubleHtml = doubleSet.has(item.name)
                    ? `<span class="badge-mini badge-double">쌍</span>`
                    : '';

                // 신고가 배지 스타일 결정
                const hpClassSuffix = CONFIG.HIGH_PRICE_CLASSES[item.high_price_type] || '';
                const highPriceClass = `badge-highprice ${hpClassSuffix}`.trim();
                
                const highPriceHtml = item.high_price_type
                    ? `<span class="${highPriceClass}">${item.high_price_type}</span>`
                    : '<span style="color: rgba(255,255,255,0.1)">-</span>';
                    
                html += `
                    <tr class="${item.is_new ? 'row-new' : ''}">
                        <td class="col-rank">${item.rank}</td>
                        <td class="col-change">${changeHtml}</td>
                        <td class="col-name">
                            <div class="name-badge-wrapper">
                                <span class="stock-name-text stock-link" data-name="${item.name}" data-ticker="${item.ticker || ''}"><strong>${item.name}</strong></span>
                                <div class="badge-container">
                                    ${consecutiveHtml}
                                    ${doubleHtml}
                                </div>
                            </div>
                        </td>
                        <td class="col-amount">${item.amount.toLocaleString()}</td>
                        <td class="col-highprice">${highPriceHtml}</td>
                    </tr>
                `;
            });

            html += `</tbody></table></div>`;
            return html;
        };

        const gridHtml = `
            <div class="stats-markets-wrapper">
                <div class="stats-market-block">
                    <h2 class="stats-market-title">KOSPI</h2>
                    <div class="stats-subject-grid">
                        ${renderSubTable('외국인', data.KOSPI.FOREIGN, kospiDouble)}
                        ${renderSubTable('기관', data.KOSPI.INSTITUTION, kospiDouble)}
                    </div>
                </div>
                <div class="stats-market-block">
                    <h2 class="stats-market-title">KOSDAQ</h2>
                    <div class="stats-subject-grid">
                        ${renderSubTable('외국인', data.KOSDAQ.FOREIGN, kosdaqDouble)}
                        ${renderSubTable('기관', data.KOSDAQ.INSTITUTION, kosdaqDouble)}
                    </div>
                </div>
            </div>
        `;
        
        container.innerHTML = gridHtml;
        this.bindEventsAfterRender(container);
    },

    /**
     * 렌더링된 요소들에 대한 후속 인터랙션(클릭 시 리다이렉션 등)을 바인딩합니다.
     * @param {HTMLElement} container - 렌더링된 요소들의 부모 DOM
     * @private
     * @returns {void}
     */
    bindEventsAfterRender(container) {
        container.querySelectorAll('.stock-link').forEach(el => {
            el.addEventListener('click', async (e) => {
                const stockName = e.currentTarget.dataset.name;
                const ticker = e.currentTarget.dataset.ticker;
                const originalContent = e.currentTarget.innerHTML;
                
                // 1. 미리 준비된 티커 정보가 있는 경우 즉시 이동
                if (ticker) {
                    window.location.href = `/stock/${ticker}`;
                    return;
                }

                // 2. 티커가 없는 경우에만 검색 API 시도
                try {
                    e.currentTarget.innerHTML = `<span style="opacity:0.6;">⏳ 검색중...</span>`;
                    const res = await fetch(`/api/stock/search?q=${encodeURIComponent(stockName)}`);
                    if (!res.ok) throw new Error('API Error');
                    const searchData = await res.json();
                    
                    if (searchData && searchData.length > 0) {
                        const ticker = searchData[0].ticker;
                        window.location.href = `/stock/${ticker}`;
                    } else {
                        alert(`종목 [${stockName}]의 정보를 시스템에서 찾을 수 없습니다.`);
                        e.currentTarget.innerHTML = originalContent;
                    }
                } catch(err) {
                    console.error('Ticker search failed:', err);
                    alert('종목 정보(티커)를 검색하는 도중 오류가 발생했습니다.');
                    e.currentTarget.innerHTML = originalContent;
                }
            });
        });
    },

    /**
     * 이전 거래일 대비 순위 변동 여부를 시각적 아이콘과 함께 반환합니다.
     * @param {Object} item - 랭킹 데이터 항목
     * @returns {string} 변동 지표 HTML
     */
    getChangeIndicator(item) {
        if (item.is_new) return '<span class="badge-new">NEW</span>';
        
        const change = item.rank_change;
        const absChange = Math.abs(change);
        
        const iconStyle = absChange >= CONFIG.RANK_CHANGE.EXPLOSIVE_THRESHOLD 
            ? 'font-size: 1.4rem; line-height: 1; transform: translateY(1px);' 
            : 'font-size: 0.8rem;';

        if (change > 0) {
            return `<span class="change-up"><span style="${iconStyle}">▲</span> ${change}</span>`;
        } else if (change < 0) {
            return `<span class="change-down"><span style="${iconStyle}">▼</span> ${absChange}</span>`;
        } else {
            return '<span class="change-none">-</span>';
        }
    }
};
