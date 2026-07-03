import { statisticsService } from '../../services/statistics_service.js';

/**
 * 주간 및 월간 등락률 뷰(Weekly & Monthly Change View) UI 모듈.
 * 연도별/주차별 주간 및 월간 상위 등락 종목 데이터를 시각화합니다.
 * 
 * @namespace
 */
export const weeklyChangeView = {
    containerId: 'statistics-container',
    currentPeriod: 'weekly', // 'weekly' or 'monthly'
    currentMarket: 'all',    // 'all', 'kospi_200', 'kosdaq_150'
    allData: [],             // 가용 날짜 목록 캐시
    currentReport: null,     // 현재 로드된 리포트
    
    /**
     * 주간/월간 등락률 탭을 초기화합니다.
     */
    async init(container) {
        this.container = container;
        this.currentPeriod = 'weekly';
        this.currentMarket = 'all';
        this.renderLayout();
        await this.loadInitialData();
    },

    /**
     * 기본 레이아웃을 렌더링합니다.
     */
    renderLayout() {
        this.container.innerHTML = `
            <div class="stats-container animate-fade-in" style="display: flex; flex-direction: column; gap: 16px;">
                <div class="stats-header" style="display: flex; justify-content: space-between; align-items: center; background: rgba(255, 255, 255, 0.02); border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 16px; padding: 16px 24px;">
                    <div class="stats-title-area" style="display: flex; align-items: center; gap: 16px;">
                        <h2 style="margin: 0; font-size: 1.3rem; display: flex; align-items: center; gap: 8px;"><i class="fas fa-chart-line" style="color: var(--accent-blue);"></i> 등락률 상위 종목</h2>
                        
                        <!-- 주간 / 월간 대분류 탭 -->
                        <div class="stats-toggle-group">
                            <button id="period-weekly" class="stats-toggle active" style="padding: 6px 12px; font-size: 0.8rem;">주간</button>
                            <button id="period-monthly" class="stats-toggle" style="padding: 6px 12px; font-size: 0.8rem;">월간</button>
                        </div>
                    </div>
                    <div class="stats-filters">
                        <div class="date-cascading-dropdown">
                            <select id="weekly-year" class="stats-select" title="연도 선택"></select>
                            <select id="weekly-week" class="stats-select" title="조회 시점 선택"></select>
                        </div>
                        <button id="weekly-refresh" class="stats-btn-refresh" title="데이터 새로고침"><i class="fas fa-sync-alt"></i></button>
                    </div>
                </div>
                
                <!-- 시장 분류 서브 탭 -->
                <div class="stats-sub-tab-container" style="display: flex; gap: 8px; background: rgba(0, 0, 0, 0.2); padding: 4px; border-radius: 12px; align-self: flex-start; border: 1px solid rgba(255, 255, 255, 0.03);">
                    <button class="stats-toggle sub-tab active" data-market="all" style="font-size: 0.8rem; padding: 6px 16px;">전체 등락종목</button>
                    <button class="stats-toggle sub-tab" data-market="kospi_200" style="font-size: 0.8rem; padding: 6px 16px;">KOSPI 200</button>
                    <button class="stats-toggle sub-tab" data-market="kosdaq_150" style="font-size: 0.8rem; padding: 6px 16px;">KOSDAQ 150</button>
                </div>

                <div id="weekly-info-container" class="weekly-meta-info"></div>
                <div id="weekly-table-container" class="stats-table-wrapper">
                    <div class="stats-loader">데이터를 불러오는 중...</div>
                </div>
            </div>
        `;

        this.attachEvents();
    },

    attachEvents() {
        const yearSelect = document.getElementById('weekly-year');
        const weekSelect = document.getElementById('weekly-week');
        const refreshBtn = document.getElementById('weekly-refresh');
        
        const periodWeekly = document.getElementById('period-weekly');
        const periodMonthly = document.getElementById('period-monthly');

        yearSelect.addEventListener('change', () => this.onYearChange());
        weekSelect.addEventListener('change', () => this.loadData());
        refreshBtn.addEventListener('click', () => this.loadData(true));

        periodWeekly.addEventListener('click', () => this.onPeriodChange('weekly'));
        periodMonthly.addEventListener('click', () => this.onPeriodChange('monthly'));

        // 서브 탭 클릭 이벤트 바인딩
        this.container.querySelectorAll('.sub-tab').forEach(btn => {
            btn.addEventListener('click', (e) => {
                this.container.querySelectorAll('.sub-tab').forEach(b => b.classList.remove('active'));
                e.currentTarget.classList.add('active');
                this.onMarketChange(e.currentTarget.dataset.market);
            });
        });
    },

    async loadInitialData() {
        try {
            const data = await statisticsService.getWeeklyChangeDates();
            this.allData = data || [];
            this.updateDateDropdowns();
        } catch (error) {
            console.error('Failed to load weekly change dates:', error);
            this.container.querySelector('#weekly-table-container').innerHTML = 
                '<div class="stats-error">데이터 로드에 실패했습니다.</div>';
        }
    },

    /**
     * 주간/월간 변경 시 드롭다운 갱신
     */
    onPeriodChange(period) {
        if (this.currentPeriod === period) return;
        this.currentPeriod = period;
        
        const wBtn = document.getElementById('period-weekly');
        const mBtn = document.getElementById('period-monthly');
        
        if (period === 'weekly') {
            wBtn.classList.add('active');
            mBtn.classList.remove('active');
        } else {
            wBtn.classList.remove('active');
            mBtn.classList.add('active');
        }

        this.updateDateDropdowns();
    },

    /**
     * 필터링된 가용 날짜 목록으로 드롭다운을 구성합니다.
     */
    updateDateDropdowns() {
        if (!this.allData || this.allData.length === 0) {
            this.container.querySelector('#weekly-table-container').innerHTML = 
                '<div class="stats-empty">데이터가 없습니다. 드라이브에서 동기화해 주세요.</div>';
            return;
        }

        const isMonthlyTarget = (this.currentPeriod === 'monthly');
        const filtered = this.allData.filter(d => !!d.is_monthly === isMonthlyTarget);

        if (filtered.length === 0) {
            document.getElementById('weekly-year').innerHTML = '';
            document.getElementById('weekly-week').innerHTML = '';
            document.getElementById('weekly-info-container').innerHTML = '';
            this.container.querySelector('#weekly-table-container').innerHTML = 
                `<div class="stats-empty">${this.currentPeriod === 'weekly' ? '주간' : '월간'} 등락률 데이터가 없습니다. 드라이브 동기화가 필요합니다.</div>`;
            return;
        }

        const years = [...new Set(filtered.map(d => String(d.year)))].sort((a, b) => b - a);
        const yearSelect = document.getElementById('weekly-year');
        yearSelect.innerHTML = years.map(y => `<option value="${y}">${y}년</option>`).join('');

        this.onYearChange();
    },

    /**
     * 연도 변경 시 해당 연도의 목록을 업데이트합니다.
     */
    onYearChange() {
        const year = document.getElementById('weekly-year').value;
        const weekSelect = document.getElementById('weekly-week');
        
        if (!year) return;

        const isMonthlyTarget = (this.currentPeriod === 'monthly');
        const yearData = this.allData.filter(d => String(d.year) === year && !!d.is_monthly === isMonthlyTarget);
        const sortedData = yearData.sort((a, b) => b.date.localeCompare(a.date));
        
        weekSelect.innerHTML = sortedData.map(d => {
            let label = '';
            if (this.currentPeriod === 'weekly') {
                label = `${d.week_num}주 (${d.month}월 ${d.week_of_month}주차)`;
            } else {
                label = `${d.month}월 (월간 등락률)`;
            }
            return `<option value="${d.date}">${label}</option>`;
        }).join('');

        this.loadData();
    },

    /**
     * 실제 데이터를 로드합니다.
     */
    async loadData(forceSync = false) {
        const tableWrapper = document.getElementById('weekly-table-container');
        const date = document.getElementById('weekly-week').value;
        
        if (!date) return;

        const refreshBtn = document.getElementById('weekly-refresh');
        const icon = refreshBtn.querySelector('i');

        try {
            refreshBtn.disabled = true;
            icon.classList.add('fa-spin');
            
            tableWrapper.innerHTML = '<div class="stats-loader"><i class="fas fa-circle-notch fa-spin"></i> 데이터를 가져오는 중...</div>';

            const report = await statisticsService.getWeeklyChange(date, forceSync);
            this.currentReport = report;
            
            this.renderInfo(report);
            this.renderTable(report);
        } catch (error) {
            tableWrapper.innerHTML = `<div class="stats-error">오류 발생: ${error.message}</div>`;
        } finally {
            refreshBtn.disabled = false;
            icon.classList.remove('fa-spin');
        }
    },

    renderInfo(report) {
        const infoWrapper = document.getElementById('weekly-info-container');
        if (!report) return;

        const isMonthly = report.is_monthly;
        const typeBadge = isMonthly 
            ? `<span class="weekly-badge range" style="border-color: rgba(239, 68, 68, 0.3); color: #f87171;"><i class="fas fa-calendar-alt"></i> 월간</span>`
            : `<span class="weekly-badge week"><i class="fas fa-calendar-week"></i> 주간 (${report.week_num}주차)</span>`;

        const detailsBadge = isMonthly
            ? `<span class="weekly-badge month">${report.month}월 누적</span>`
            : `<span class="weekly-badge month">${report.month}월 ${report.week_of_month}주차</span>`;

        infoWrapper.innerHTML = `
            <div class="weekly-badge-group" style="margin-top: 4px;">
                <span class="weekly-badge year">${report.year}년</span>
                ${typeBadge}
                ${detailsBadge}
                <span class="weekly-badge range"><i class="far fa-calendar-alt"></i> ${report.date_range || report.date}</span>
            </div>
        `;
    },

    onMarketChange(market) {
        if (this.currentMarket === market) return;
        this.currentMarket = market;
        this.renderTable(this.currentReport);
    },

    renderTable(report) {
        const container = document.getElementById('weekly-table-container');
        if (!report) {
            container.innerHTML = '<div class="stats-empty">데이터가 없습니다.</div>';
            return;
        }

        let items = [];
        if (this.currentMarket === 'all') {
            items = report.items || [];
        } else if (this.currentMarket === 'kospi_200') {
            items = report.kospi_200_items || [];
        } else if (this.currentMarket === 'kosdaq_150') {
            items = report.kosdaq_150_items || [];
        }

        if (items.length === 0) {
            container.innerHTML = '<div class="stats-empty" style="padding: 40px; color: var(--text-secondary); text-align: center;">해당 조건의 등락률 데이터가 존재하지 않습니다.<br><span style="font-size: 0.8rem; opacity: 0.7;">(과거 데이터에는 KOSPI 200 / KOSDAQ 150 시트가 없을 수 있습니다)</span></div>';
            return;
        }

        let html = `
            <table class="stats-table animate-fade-in">
                <thead>
                    <tr>
                        <th style="width: 60px;">순위</th>
                        <th>종목명</th>
                        <th style="text-align: right;">종가(종료일)</th>
                        <th style="text-align: right;">기준가(시작일)</th>
                        <th style="text-align: center;">등락률</th>
                    </tr>
                </thead>
                <tbody>
        `;

        items.forEach((item, idx) => {
            const changeClass = item.change_rate > 0 ? 'change-up' : (item.change_rate < 0 ? 'change-down' : 'change-none');
            const changeSign = item.change_rate > 0 ? '+' : '';
            
            html += `
                <tr class="stats-tr-hover" style="transition: background 0.15s ease;">
                    <td class="col-rank">${idx + 1}</td>
                    <td class="col-name">
                        <span class="stock-name-text stock-link" data-name="${item.name}" style="cursor: pointer; text-decoration: none; border-bottom: 1px dotted rgba(255,255,255,0.1); transition: border 0.2s;">${item.name}</span>
                    </td>
                    <td style="text-align: right; font-weight: 500;">${item.close_price.toLocaleString()}원</td>
                    <td style="text-align: right; color: rgba(255,255,255,0.4); font-size: 0.85rem;">${item.base_price.toLocaleString()}원</td>
                    <td style="text-align: center;">
                        <span class="change-badge ${changeClass}">${changeSign}${item.change_rate.toFixed(2)}%</span>
                    </td>
                </tr>
            `;
        });

        html += '</tbody></table>';
        container.innerHTML = html;

        this.bindEvents(container);
    },

    bindEvents(container) {
        container.querySelectorAll('.stock-link').forEach(el => {
            el.addEventListener('click', async (e) => {
                const stockName = e.currentTarget.dataset.name;
                try {
                    const res = await fetch(`/api/stock/search?q=${encodeURIComponent(stockName)}`);
                    const data = await res.json();
                    if (data && data.length > 0) {
                        window.location.href = `/stock/${data[0].ticker}`;
                    }
                } catch (err) {
                    console.error('Search failed:', err);
                }
            });
            // hover style trigger
            el.addEventListener('mouseenter', (e) => {
                e.currentTarget.style.color = 'var(--accent-blue)';
                e.currentTarget.style.borderBottomColor = 'var(--accent-blue)';
            });
            el.addEventListener('mouseleave', (e) => {
                el.style.color = '';
                el.style.borderBottomColor = '';
            });
        });

        // 행 hover 효과 추가
        container.querySelectorAll('.stats-tr-hover').forEach(tr => {
            tr.addEventListener('mouseenter', (e) => {
                e.currentTarget.style.background = 'rgba(255, 255, 255, 0.03)';
            });
            tr.addEventListener('mouseleave', (e) => {
                e.currentTarget.style.background = '';
            });
        });
    }
};
