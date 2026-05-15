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
    sortConfig: { key: 'change_rate', direction: 'desc' }, // 정렬 설정

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
                        <button class="stats-toggle ${this.turnaroundMode === 'NORMAL' ? 'active' : ''}" data-value="NORMAL">일반 성장</button>
                        <button class="stats-toggle ${this.turnaroundMode === 'TURNAROUND' ? 'active' : ''}" data-value="TURNAROUND">흑자 전환</button>
                    </div>
                </div>
                <button id="fin-refresh-btn" class="analysis-btn-primary">
                    <i class="fas fa-sync-alt"></i> 분석 업데이트
                </button>
            </div>

            <div id="fin-table-container" class="stats-table-wrapper"></div>
        `;

        this.bindEvents();
        
        // 현재 상태 복원
        const metricSelect = this.container.querySelector('#fin-metric-select');
        if (metricSelect) metricSelect.value = this.currentMetric;

        await this.loadQuarters();
        await this.loadData();
    },

    bindEvents() {
        const metricSelect = this.container.querySelector('#fin-metric-select');
        const quarterSelect = this.container.querySelector('#fin-quarter-select');
        const turnaroundToggle = this.container.querySelector('#fin-turnaround-toggle');
        const refreshBtn = this.container.querySelector('#fin-refresh-btn');
        const tableContainer = this.container.querySelector('#fin-table-container');

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

        // 테이블 헤더 클릭 시 정렬 (이벤트 위임 - 테이블 컨테이너에 바인딩하여 뷰 전환 시 자동 소멸되도록 함)
        tableContainer?.addEventListener('click', (e) => {
            const th = e.target.closest('th[data-sort]');
            if (!th) return;

            const key = th.dataset.sort;
            if (this.sortConfig.key === key) {
                this.sortConfig.direction = this.sortConfig.direction === 'desc' ? 'asc' : 'desc';
            } else {
                this.sortConfig.key = key;
                this.sortConfig.direction = 'desc';
            }
            this.renderTable();
        });
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
        
        let filteredItems = [...(this.turnaroundMode === 'TURNAROUND' 
            ? this.allData.turnaround 
            : this.allData.normal)];

        // 정렬 적용
        if (this.sortConfig.key) {
            filteredItems.sort((a, b) => {
                const valA = a[this.sortConfig.key];
                const valB = b[this.sortConfig.key];
                if (this.sortConfig.direction === 'asc') {
                    return valA - valB;
                } else {
                    return valB - valA;
                }
            });
        }

        if (filteredItems.length === 0) {
            container.innerHTML = '<div class="stats-empty">조건에 맞는 데이터가 없습니다.</div>';
            return;
        }

        const getSortIcon = (key) => {
            if (this.sortConfig.key !== key) return '<i class="fas fa-sort" style="margin-left: 5px; opacity: 0.3;"></i>';
            return this.sortConfig.direction === 'desc' 
                ? '<i class="fas fa-sort-down" style="margin-left: 5px; color: var(--accent-blue);"></i>' 
                : '<i class="fas fa-sort-up" style="margin-left: 5px; color: var(--accent-blue);"></i>';
        };

        let html = `
            <table class="stats-table">
                <thead>
                    <tr>
                        <th style="width: 50px; text-align: center;">순위</th>
                        <th style="min-width: 150px;">종목명</th>
                        <th style="text-align: right; min-width: 100px; color: #facc15;">이전 분기</th>
                        <th style="text-align: right; min-width: 100px;">직전 분기</th>
                        <th data-sort="current_value" style="text-align: right; min-width: 100px; cursor: pointer; user-select: none;">
                            해당 분기 ${getSortIcon('current_value')}
                        </th>
                        <th data-sort="change_rate" style="text-align: center; width: 140px; cursor: pointer; user-select: none;">
                            등락률 (QoQ) ${getSortIcon('change_rate')}
                        </th>
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
