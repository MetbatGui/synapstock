import { statisticsService } from '../../services/statistics_service.js';

/**
 * 주간 등락률 뷰(Weekly Change View) UI 모듈.
 * 연도별/주차별 주간 상위 등락 종목 데이터를 시각화합니다.
 * 
 * @namespace
 */
export const weeklyChangeView = {
    containerId: 'statistics-container',
    
    /**
     * 주간 등락률 탭을 초기화합니다.
     */
    async init(container) {
        this.container = container;
        this.renderLayout();
        await this.loadInitialData();
    },

    /**
     * 기본 레이아웃을 렌더링합니다.
     */
    renderLayout() {
        this.container.innerHTML = `
            <div class="stats-container animate-fade-in">
                <div class="stats-header">
                    <h2><i class="fas fa-chart-line"></i> 주간 등락 상위 종목</h2>
                    <div class="stats-filters">
                        <div class="date-cascading-dropdown">
                            <select id="weekly-year" class="stats-select" title="연도 선택"></select>
                            <select id="weekly-week" class="stats-select" title="주차 선택"></select>
                        </div>
                        <button id="weekly-refresh" class="stats-btn-refresh" title="데이터 새로고침"><i class="fas fa-sync-alt"></i></button>
                    </div>
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

        yearSelect.addEventListener('change', () => this.onYearChange());
        weekSelect.addEventListener('change', () => this.loadData());
        refreshBtn.addEventListener('click', () => this.loadData(true));
    },

    async loadInitialData() {
        await this.updateDateList();
    },

    /**
     * 가용 날짜 목록을 가져와 드롭다운을 구성합니다.
     */
    async updateDateList() {
        try {
            const data = await statisticsService.getWeeklyChangeDates();
            if (!data || data.length === 0) {
                this.container.querySelector('#weekly-table-container').innerHTML = 
                    '<div class="stats-empty">데이터가 없습니다. 드라이브에서 동기화해 주세요.</div>';
                return;
            }

            this.allData = data; // 메타데이터 포함 캐시

            // 연도 목록 추출
            const years = [...new Set(data.map(d => String(d.year)))].sort((a, b) => b - a);
            const yearSelect = document.getElementById('weekly-year');
            yearSelect.innerHTML = years.map(y => `<option value="${y}">${y}년</option>`).join('');

            await this.onYearChange();
        } catch (error) {
            console.error('Failed to update weekly change dates:', error);
        }
    },

    /**
     * 연도 변경 시 해당 연도의 주차 목록을 업데이트합니다.
     */
    async onYearChange() {
        const year = document.getElementById('weekly-year').value;
        const weekSelect = document.getElementById('weekly-week');
        
        // 해당 연도의 데이터들만 필터링
        const yearData = this.allData.filter(d => String(d.year) === year);
        
        // 날짜 순 정렬 (최신순)
        const sortedData = yearData.sort((a, b) => b.date.localeCompare(a.date));
        
        // 드롭다운 구성 (19주 (5월 1주차) 형식)
        weekSelect.innerHTML = sortedData.map(d => {
            const label = `${d.week_num}주 (${d.month}월 ${d.week_of_month}주차)`;
            return `<option value="${d.date}">${label}</option>`;
        }).join('');

        await this.loadData();
    },

    /**
     * 실제 데이터를 로드하여 테이블을 렌더링합니다.
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
            
            this.renderInfo(report);
            this.renderTable(report);
        } catch (error) {
            tableWrapper.innerHTML = `<div class="stats-error">오류 발생: ${error.message}</div>`;
        } finally {
            refreshBtn.disabled = false;
            icon.classList.remove('fa-spin');
        }
    },

    /**
     * 드롭다운의 날짜 레이블을 "19주 (5월 1주차)" 형식으로 보강합니다.
     */
    updateWeekLabel(report) {
        if (!report || !report.week_num) return;
        
        const weekSelect = document.getElementById('weekly-week');
        const option = weekSelect.querySelector(`option[value="${report.date}"]`);
        if (option) {
            const label = `${report.week_num}주 (${report.month}월 ${report.week_of_month}주차)`;
            option.textContent = label;
        }
    },

    renderInfo(report) {
        const infoWrapper = document.getElementById('weekly-info-container');
        if (!report) return;

        infoWrapper.innerHTML = `
            <div class="weekly-badge-group">
                <span class="weekly-badge year">${report.year}년</span>
                <span class="weekly-badge week">${report.week_num}주차</span>
                <span class="weekly-badge month">${report.month}월 ${report.week_of_month}주차</span>
                <span class="weekly-badge range"><i class="far fa-calendar-alt"></i> ${report.date_range || report.date}</span>
            </div>
        `;
    },

    renderTable(report) {
        const container = document.getElementById('weekly-table-container');
        if (!report || !report.items || report.items.length === 0) {
            container.innerHTML = '<div class="stats-empty">데이터가 없습니다.</div>';
            return;
        }

        let html = `
            <table class="stats-table animate-fade-in">
                <thead>
                    <tr>
                        <th style="width: 60px;">순위</th>
                        <th>종목명</th>
                        <th style="text-align: right;">현재가</th>
                        <th style="text-align: right;">전주종가</th>
                        <th style="text-align: center;">주간 등락률</th>
                    </tr>
                </thead>
                <tbody>
        `;

        report.items.forEach((item, idx) => {
            const changeClass = item.change_rate > 0 ? 'change-up' : (item.change_rate < 0 ? 'change-down' : 'change-none');
            const changeSign = item.change_rate > 0 ? '+' : '';
            
            html += `
                <tr>
                    <td class="col-rank">${idx + 1}</td>
                    <td class="col-name">
                        <span class="stock-name-text stock-link" data-name="${item.name}">${item.name}</span>
                    </td>
                    <td style="text-align: right;">${item.current_price.toLocaleString()}원</td>
                    <td style="text-align: right; color: #888;">${item.prev_week_close.toLocaleString()}원</td>
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
        });
    }
};
