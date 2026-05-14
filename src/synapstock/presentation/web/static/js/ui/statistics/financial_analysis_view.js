import { financialService } from '../../services/financial_service.js';

/**
 * 재무제표 분석(Financial Analysis) 뷰 모듈.
 */
export const financialAnalysisView = {
    container: null,
    currentMetric: 'OPERATING_PROFIT',
    currentQuarter: null,
    turnaroundMode: 'NORMAL', // 'NORMAL' or 'TURNAROUND'
    allData: { normal: [], turnaround: [] }, // 전체 데이터 보관용

    async init(container) {
        this.container = container || document.getElementById('stats-content');
        if (!this.container) return;

        this.container.innerHTML = `
            <div class="stats-header-actions">
                <div class="stats-title-group">
                    <h2 class="stats-content-title">재무제표 분석 (QoQ)</h2>
                    <p class="stats-content-desc">선택한 분기의 직전 분기 대비 실적 개선 종목을 분석합니다.</p>
                </div>
            </div>

            <div class="analysis-toolbar">
                <div class="control-group">
                    <label>기준 분기</label>
                    <select id="fin-quarter-select" class="analysis-select">
                        <option value="">로딩 중...</option>
                    </select>
                </div>
                <div class="control-group">
                    <label>재무 지표</label>
                    <select id="fin-metric-select" class="analysis-select">
                        <option value="REVENUE">매출액</option>
                        <option value="OPERATING_PROFIT" selected>영업이익</option>
                        <option value="NET_INCOME">당기순이익</option>
                    </select>
                </div>
                <div class="control-group">
                    <label>분석 유형</label>
                    <div class="stats-toggle-group" id="fin-turnaround-toggle">
                        <button class="stats-toggle active" data-value="NORMAL">일반 성장</button>
                        <button class="stats-toggle" data-value="TURNAROUND">흑자 전환</button>
                    </div>
                </div>
                <button id="fin-refresh-btn" class="analysis-btn-primary">
                    <i class="fas fa-sync-alt"></i> 분석 업데이트
                </button>
            </div>

            <div id="fin-table-container" class="stats-table-wrapper"></div>
        `;

        this.bindEvents();
        await this.loadQuarters();
        await this.loadData();
    },

    bindEvents() {
        const metricSelect = document.getElementById('fin-metric-select');
        const quarterSelect = document.getElementById('fin-quarter-select');
        const turnaroundToggle = document.getElementById('fin-turnaround-toggle');
        const refreshBtn = document.getElementById('fin-refresh-btn');

        metricSelect?.addEventListener('change', async (e) => {
            this.currentMetric = e.target.value;
            await this.loadQuarters();
            await this.loadData();
        });

        quarterSelect?.addEventListener('change', (e) => {
            this.currentQuarter = e.target.value;
            this.loadData();
        });

        turnaroundToggle?.addEventListener('click', (e) => {
            const btn = e.target.closest('.stats-toggle');
            if (!btn) return;

            turnaroundToggle.querySelectorAll('.stats-toggle').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            
            this.turnaroundMode = btn.dataset.value;
            this.renderTable(); // 로컬 데이터로 토글
        });

        refreshBtn?.addEventListener('click', () => this.loadData());
    },

    async loadQuarters() {
        try {
            const quarters = await financialService.getQuarters(this.currentMetric);
            const select = document.getElementById('fin-quarter-select');
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
        const tableContainer = document.getElementById('fin-table-container');
        if (!tableContainer) return;
        
        tableContainer.innerHTML = '<div class="stats-loader"><i class="fas fa-spinner fa-spin"></i> 데이터 분석 중...</div>';

        try {
            const data = await financialService.getTopGrowers(
                this.currentMetric, 
                this.currentQuarter, 
                500
            );
            this.allData = data; // {normal: [], turnaround: []}
            this.renderTable();
        } catch (error) {
            tableContainer.innerHTML = `<div class="stats-error">오류 발생: ${error.message}</div>`;
        }
    },

    renderTable() {
        const container = document.getElementById('fin-table-container');
        if (!container) return;
        
        const filteredItems = this.turnaroundMode === 'TURNAROUND' 
            ? this.allData.turnaround 
            : this.allData.normal;

        if (filteredItems.length === 0) {
            container.innerHTML = '<div class="stats-empty">조건에 맞는 데이터가 없습니다.</div>';
            return;
        }

        let html = `
            <table class="stats-table">
                <thead>
                    <tr>
                        <th style="width: 50px; text-align: center;">순위</th>
                        <th style="min-width: 150px;">종목명</th>
                        <th style="text-align: right; min-width: 100px; color: #facc15;">이전 분기</th>
                        <th style="text-align: right; min-width: 100px;">직전 분기</th>
                        <th style="text-align: right; min-width: 100px;">해당 분기</th>
                        <th style="text-align: center; width: 120px;">등락률 (QoQ)</th>
                    </tr>
                </thead>
                <tbody>
        `;

        filteredItems.forEach((item, index) => {
            const rate = item.change_rate;
            const isPositive = rate > 0;
            const isNegative = rate < 0;
            
            const rateColor = isPositive ? '#ff4d4d' : (isNegative ? '#4d94ff' : '#fff');
            const rateSymbol = isPositive ? '▲' : (isNegative ? '▼' : '-');
            
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
                    <td style="text-align: right; color: #facc15; background: rgba(250, 204, 21, 0.05);">
                        ${item.pre_prev_value !== null ? Math.round(item.pre_prev_value).toLocaleString() : '-'}
                    </td>
                    <td style="text-align: right; color: rgba(255,255,255,0.6);">
                        ${Math.round(item.prev_value).toLocaleString()}
                    </td>
                    <td style="text-align: right; font-weight: 600; color: #fff;">
                        ${Math.round(item.current_value).toLocaleString()}
                    </td>
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
