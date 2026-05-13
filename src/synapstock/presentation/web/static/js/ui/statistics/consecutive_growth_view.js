import { financialService } from '../../services/financial_service.js';

/**
 * 연속 실적 성장주 분석 뷰
 */
export const consecutiveGrowthView = {
    container: null,
    currentMetric: 'OPERATING_PROFIT',
    currentQuarter: null,
    currentCount: 3, 
    excludeTurnaround: false,
    allData: [],

    async init(container) {
        this.container = container || document.getElementById('stats-content');
        if (!this.container) return;

        this.container.innerHTML = `
            <div class="stats-header-actions">
                <div class="stats-title-group">
                    <h2 class="stats-content-title">연속 실적 성장주 분석</h2>
                    <p class="stats-content-desc">지정한 분기부터 과거 N분기 동안 실적이 매분기 우상향한 '알짜' 종목을 발굴합니다.</p>
                </div>
            </div>

            <div class="analysis-toolbar">
                <div class="control-group">
                    <label>상승 기간</label>
                    <select id="grow-count-select" class="analysis-select">
                        <option value="2">2분기 연속</option>
                        <option value="3" selected>3분기 연속</option>
                        <option value="4">4분기 연속</option>
                    </select>
                </div>
                <div class="control-group">
                    <label>기준 분기</label>
                    <select id="grow-quarter-select" class="analysis-select">
                        <option value="">로딩 중...</option>
                    </select>
                </div>
                <div class="control-group">
                    <label>분석 지표</label>
                    <select id="grow-metric-select" class="analysis-select">
                        <option value="REVENUE">매출액</option>
                        <option value="OPERATING_PROFIT" selected>영업이익</option>
                        <option value="NET_INCOME">당기순이익</option>
                    </select>
                </div>
                <div class="analysis-check-group">
                    <input type="checkbox" id="grow-exclude-turnaround">
                    <span>흑자전환 제외</span>
                </div>
                <button id="grow-refresh-btn" class="analysis-btn-primary">
                    <i class="fas fa-search"></i> 분석 시작
                </button>
            </div>

            <div id="grow-table-container" class="stats-table-wrapper"></div>
        `;

        this.bindEvents();
        await this.loadQuarters();
        await this.loadData();
    },

    bindEvents() {
        const metricSelect = document.getElementById('grow-metric-select');
        const quarterSelect = document.getElementById('grow-quarter-select');
        const countSelect = document.getElementById('grow-count-select');
        const turnaroundCheck = document.getElementById('grow-exclude-turnaround');
        const refreshBtn = document.getElementById('grow-refresh-btn');

        metricSelect?.addEventListener('change', async (e) => {
            this.currentMetric = e.target.value;
            await this.loadQuarters();
            await this.loadData();
        });

        quarterSelect?.addEventListener('change', (e) => {
            this.currentQuarter = e.target.value;
            this.loadData();
        });

        countSelect?.addEventListener('change', (e) => {
            this.currentCount = parseInt(e.target.value);
            this.loadData();
        });

        turnaroundCheck?.addEventListener('change', (e) => {
            this.excludeTurnaround = e.target.checked;
            this.renderTable(this.allData);
        });

        refreshBtn?.addEventListener('click', () => this.loadData());
    },

    async loadQuarters() {
        try {
            const quarters = await financialService.getQuarters(this.currentMetric);
            const select = document.getElementById('grow-quarter-select');
            if (!select || !quarters.length) return;

            const currentValue = select.value;
            select.innerHTML = quarters.map(q => `<option value="${q}">${q}</option>`).join('');
            
            if (currentValue && quarters.includes(currentValue)) {
                select.value = currentValue;
            } else {
                select.value = quarters[0];
                this.currentQuarter = quarters[0];
            }
        } catch (error) {
            console.error('Failed to load quarters:', error);
        }
    },

    async loadData() {
        const tableContainer = document.getElementById('grow-table-container');
        if (!tableContainer) return;
        
        tableContainer.innerHTML = '<div class="stats-loader"><i class="fas fa-spinner fa-spin"></i> 연속 성장주 탐색 중...</div>';

        try {
            const data = await financialService.getConsecutiveGrowers(this.currentMetric, this.currentQuarter, this.currentCount);
            this.allData = data;
            this.renderTable(data);
        } catch (error) {
            tableContainer.innerHTML = `<div class="stats-error">오류 발생: ${error.message}</div>`;
        }
    },

    renderTable(items) {
        const container = document.getElementById('grow-table-container');
        if (!container) return;
        
        // 필터링 적용
        let filteredItems = items || [];
        if (this.excludeTurnaround) {
            filteredItems = filteredItems.filter(item => !(item.prev_value <= 0 && item.current_value > 0));
        }

        if (filteredItems.length === 0) {
            container.innerHTML = `<div class="stats-empty">조건에 맞는 데이터를 찾지 못했습니다.</div>`;
            return;
        }

        // 히스토리 헤더 구성
        const firstItem = filteredItems[0];
        const quarters = Object.keys(firstItem.history).sort();

        let html = `
            <table class="stats-table">
                <thead>
                    <tr>
                        <th style="width: 50px; text-align: center;">순위</th>
                        <th style="min-width: 150px;">종목명</th>
                        ${quarters.map(q => `<th style="text-align: right; min-width: 90px;">${q}</th>`).join('')}
                        <th style="text-align: center; width: 110px;">전체 성장률</th>
                    </tr>
                </thead>
                <tbody>
        `;

        filteredItems.forEach((item, index) => {
            const rate = item.change_rate;
            const isPositive = rate > 0;
            const rateColor = isPositive ? '#ff4d4d' : '#fff';
            const rateSymbol = isPositive ? '▲' : '';
            
            // 흑자 전환 강조
            const isTurnaround = item.prev_value <= 0 && item.current_value > 0;
            
            html += `
                <tr>
                    <td style="text-align: center; color: #9ca3af; font-size: 0.85rem;">${index + 1}</td>
                    <td>
                        <div class="name-badge-wrapper">
                            <span class="stock-name-text stock-link" onclick="window._jumpToStock('${item.ticker || ''}', '${item.stock_name}')" style="cursor:pointer; font-weight: 600;">
                                ${item.stock_name}
                            </span>
                            ${isTurnaround ? '<span class="badge-mini" style="background: #facc15; color: #000;">흑자전환</span>' : ''}
                        </div>
                    </td>
                    ${quarters.map(q => {
                        const val = item.history[q] || 0;
                        const isLatest = q === quarters[quarters.length - 1];
                        const valColor = isLatest ? '#fff' : 'rgba(255,255,255,0.5)';
                        return `<td style="text-align: right; font-family: 'Inter'; color: ${valColor};">${Math.round(val).toLocaleString()}</td>`;
                    }).join('')}
                    <td style="text-align: center; color: ${rateColor}; font-weight: bold; background: rgba(255,255,255,0.02);">
                        ${rateSymbol} ${Math.abs(rate).toLocaleString()}%
                    </td>
                </tr>
            `;
        });

        html += `</tbody></table>`;
        container.innerHTML = html;
    }
};
