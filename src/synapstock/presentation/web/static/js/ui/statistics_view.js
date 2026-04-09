/**
 * 통계 뷰(Statistics View) UI 모듈.
 * 수급 순위표 및 필터 렌더링을 담당합니다.
 */
import { statisticsService } from '../services/statistics_service.js';

export const statisticsView = {
    containerId: 'statistics-view',
    
    /**
     * 통계 탭 초기화 및 렌더링
     */
    async init(container) {
        this.container = container;
        this.renderLayout();
        await this.loadInitialData();
    },

    /**
     * 전체 레이아웃 (필터 + 결과 영역) 렌더링
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

    attachEvents() {
        const dateSelect = document.getElementById('stats-date');
        const refreshBtn = document.getElementById('stats-refresh');

        dateSelect.addEventListener('change', () => this.loadData());
        refreshBtn.addEventListener('click', () => this.handleSync());
    },

    /**
     * 클라우드 동기화 처리
     */
    async handleSync() {
        const refreshBtn = document.getElementById('stats-refresh');
        const icon = refreshBtn.querySelector('i');
        
        try {
            refreshBtn.disabled = true;
            icon.classList.add('fa-spin');
            
            const result = await statisticsService.syncStatistics();
            console.log('Sync result:', result);
            
            // 동기화 후 목록 갱신 및 데이터 로드
            await this.updateDateList();
            await this.loadData();
            
            // 성공 알림 (간단하게 콘솔이나 토스트 등으로 확장 가능)
        } catch (error) {
            console.error('Sync failed:', error);
            alert('동기화 실패: ' + error.message);
        } finally {
            refreshBtn.disabled = false;
            icon.classList.remove('fa-spin');
        }
    },

    /**
     * 초기 데이터(날짜 목록 등) 로드
     */
    async loadInitialData() {
        await this.updateDateList();
        await this.loadData();
    },

    async updateDateList() {
        // 날짜 목록은 KOSPI/FOREIGN 기준으로 가져옴 (동기화 단위가 같으므로 동일함)
        const dates = await statisticsService.getAvailableDates('KOSPI', 'FOREIGN');
        
        const dateSelect = document.getElementById('stats-date');
        const currentVal = dateSelect.value;
        
        dateSelect.innerHTML = dates.map(d => `<option value="${d}">${d}</option>`).join('');
        
        // 기존 선택값이 목록에 있으면 유지, 없으면 최신 날짜
        if (dates.includes(currentVal)) {
            dateSelect.value = currentVal;
        } else if (dates.length > 0) {
            dateSelect.value = dates[0];
        }
    },

    /**
     * 선택된 필터에 따라 실제 데이터 로드 및 렌더링
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

    renderSummaryGrid(data) {
        const container = document.getElementById('stats-table-container');
        if (!data || !data.KOSPI || !data.KOSDAQ) {
            container.innerHTML = '<div class="stats-empty">표시할 데이터가 없습니다.</div>';
            return;
        }

        const getIntersection = (catF, catI) => {
            const setF = new Set(catF?.items?.map(i => i.name) || []);
            const setI = new Set(catI?.items?.map(i => i.name) || []);
            return new Set([...setF].filter(x => setI.has(x)));
        };

        const kospiDouble = getIntersection(data.KOSPI.FOREIGN, data.KOSPI.INSTITUTION);
        const kosdaqDouble = getIntersection(data.KOSDAQ.FOREIGN, data.KOSDAQ.INSTITUTION);

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
                            </tr>
                        </thead>
                        <tbody>
            `;

            rankingData.items.forEach(item => {
                const changeHtml = this.getChangeIndicator(item);
                const consecutiveHtml = item.consecutive_days > 1 
                    ? `<span class="badge-mini badge-consecutive">🔥 ${item.consecutive_days}</span>`
                    : '';
                const doubleHtml = doubleSet.has(item.name)
                    ? `<span class="badge-mini badge-double">쌍</span>`
                    : '';
                    
                html += `
                    <tr class="${item.is_new ? 'row-new' : ''}">
                        <td class="col-rank">${item.rank}</td>
                        <td class="col-change">${changeHtml}</td>
                        <td class="col-name">
                            <div class="name-badge-wrapper">
                                <span class="stock-name-text"><strong>${item.name}</strong></span>
                                <div class="badge-container">
                                    ${consecutiveHtml}
                                    ${doubleHtml}
                                </div>
                            </div>
                        </td>
                        <td class="col-amount">${item.amount.toLocaleString()}</td>
                    </tr>
                `;
            });

            html += `</tbody></table></div>`;
            return html;
        };

        let html = `
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
        
        container.innerHTML = html;
    },

    getChangeIndicator(item) {
        if (item.is_new) return '<span class="badge-new">NEW</span>';
        
        const change = item.rank_change;
        const absChange = Math.abs(change);
        
        // 10단계 이상 변동이면 두 자릿수(폭발적) 진입이므로 삼각형 크기를 눈에 띄게 키움
        const iconStyle = absChange >= 10 
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
