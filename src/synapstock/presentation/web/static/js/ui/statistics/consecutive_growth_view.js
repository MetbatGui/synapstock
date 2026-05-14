import { financialService } from '../../services/financial_service.js';

/**
 * 연속 실적 성장주 분석 뷰
 */
export const consecutiveGrowthView = {
    container: null,
    currentMetric: 'OPERATING_PROFIT',
    currentQuarter: null,
    currentCount: 3, 
    turnaroundMode: 'NORMAL', // 'NORMAL' or 'TURNAROUND'
    allData: { normal: [], turnaround: [] },
    sortConfig: { key: 'current_value', direction: 'desc' }, // 정렬 설정 (기본 실적규모순)

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
                <div class="control-group">
                    <label>분석 유형</label>
                    <div class="stats-toggle-group" id="grow-turnaround-toggle">
                        <button class="stats-toggle ${this.turnaroundMode === 'NORMAL' ? 'active' : ''}" data-value="NORMAL">일반 성장</button>
                        <button class="stats-toggle ${this.turnaroundMode === 'TURNAROUND' ? 'active' : ''}" data-value="TURNAROUND">흑자 전환</button>
                    </div>
                </div>
                <button id="grow-refresh-btn" class="analysis-btn-primary">
                    <i class="fas fa-search"></i> 분석 시작
                </button>
            </div>

            <div id="grow-table-container" class="stats-table-wrapper"></div>
        `;

        this.bindEvents();
        
        // 현재 상태 복원
        const metricSelect = this.container.querySelector('#grow-metric-select');
        if (metricSelect) metricSelect.value = this.currentMetric;
        
        const countSelect = this.container.querySelector('#grow-count-select');
        if (countSelect) countSelect.value = this.currentCount;

        await this.loadQuarters();
        await this.loadData();
    },

    bindEvents() {
        const metricSelect = this.container.querySelector('#grow-metric-select');
        const quarterSelect = this.container.querySelector('#grow-quarter-select');
        const countSelect = this.container.querySelector('#grow-count-select');
        const turnaroundToggle = this.container.querySelector('#grow-turnaround-toggle');
        const refreshBtn = this.container.querySelector('#grow-refresh-btn');
        const tableContainer = this.container.querySelector('#grow-table-container');

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

        turnaroundToggle?.addEventListener('click', (e) => {
            const btn = e.target.closest('.stats-toggle');
            if (!btn) return;

            turnaroundToggle.querySelectorAll('.stats-toggle').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            
            this.turnaroundMode = btn.dataset.value;
            this.renderTable();
        });

        refreshBtn?.addEventListener('click', () => this.loadData());

        // 테이블 헤더 클릭 시 정렬
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
            const data = await financialService.getConsecutiveGrowers(
                this.currentMetric, 
                this.currentQuarter, 
                this.currentCount
            );
            this.allData = data;
            this.renderTable();
        } catch (error) {
            tableContainer.innerHTML = `<div class="stats-error">오류 발생: ${error.message}</div>`;
        }
    },

    renderTable() {
        const container = document.getElementById('grow-table-container');
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
            container.innerHTML = `<div class="stats-empty">조건에 맞는 데이터를 찾지 못했습니다.</div>`;
            return;
        }

        // 히스토리 헤더 구성
        const firstItem = filteredItems[0];
        const quarters = Object.keys(firstItem.history).sort();

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
                        ${quarters.map((q, i) => {
                            const isLatest = i === quarters.length - 1;
                            const isPreStart = i === 0;
                            const style = `text-align: right; min-width: 90px; ${isPreStart ? 'color: #facc15;' : ''} ${isLatest ? 'cursor: pointer; user-select: none;' : ''}`;
                            const sortAttr = isLatest ? 'data-sort="current_value"' : '';
                            return `<th ${sortAttr} style="${style}">${q}${isLatest ? ' ' + getSortIcon('current_value') : ''}</th>`;
                        }).join('')}
                        <th data-sort="change_rate" style="text-align: center; width: 110px; cursor: pointer; user-select: none;">
                            전체 성장률 ${getSortIcon('change_rate')}
                        </th>
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
                    ${quarters.map((q, i) => {
                        const val = item.history[q] || 0;
                        const isLatest = q === quarters[quarters.length - 1];
                        const isPreStart = i === 0;
                        let valColor = isLatest ? '#fff' : 'rgba(255,255,255,0.5)';
                        let bgStyle = '';
                        
                        if (isPreStart) {
                            valColor = '#facc15';
                            bgStyle = 'background: rgba(250, 204, 21, 0.05);';
                        }
                        
                        return `<td style="text-align: right; font-family: 'Inter'; color: ${valColor}; ${bgStyle}">${Math.round(val).toLocaleString()}</td>`;
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
