import { statisticsService } from '../services/statistics_service.js';

/**
 * 상한가 분석 뷰(Ceiling Analysis View) UI 모듈.
 * 일자별 상한가 종목들의 10일치 가격 추이를 시각화하고 동기화 기능을 제공합니다.
 * 
 * @namespace
 */
export const ceilingView = {
    /** @type {string} */
    containerId: 'statistics-container',
    
    /**
     * 상한가 분석 탭을 초기화합니다.
     * @param {HTMLElement} container - 뷰가 렌더링될 DOM 컨테이너
     * @returns {Promise<void>}
     */
    async init(container) {
        this.container = container;
        this.renderLayout();
        await this.loadInitialData();
    },

    /**
     * 기본 레이아웃을 렌더링합니다.
     * @returns {void}
     */
    renderLayout() {
        this.container.innerHTML = `
            <div class="stats-container animate-fade-in">
                <div class="stats-header">
                    <h2><i class="fas fa-crown"></i> 상한가 종목 추적 분석</h2>
                    <div class="stats-filters">
                        <select id="ceiling-date" class="stats-select"></select>
                        <button id="ceiling-refresh" class="stats-btn-refresh" title="원시 데이터 다시 가져오기"><i class="fas fa-sync-alt"></i></button>
                    </div>
                </div>
                <div id="ceiling-table-container" class="stats-table-wrapper">
                    <div class="stats-loader">분석 데이터를 불러오는 중...</div>
                </div>
            </div>
        `;

        this.attachEvents();
    },

    /**
     * 이벤트 리스너를 바인딩합니다.
     * @private
     */
    attachEvents() {
        const dateSelect = document.getElementById('ceiling-date');
        const refreshBtn = document.getElementById('ceiling-refresh');

        dateSelect.addEventListener('change', () => this.loadData());
        refreshBtn.addEventListener('click', () => this.loadData(true));
    },

    /**
     * 초기 데이터를 로드합니다.
     * @async
     */
    async loadInitialData() {
        await this.updateDateList();
        await this.loadData();
    },

    /**
     * 가용 날짜 목록을 업데이트합니다.
     * @async
     */
    async updateDateList() {
        try {
            const dates = await statisticsService.getCeilingDates();
            const dateSelect = document.getElementById('ceiling-date');
            if (!dateSelect) return;

            const currentVal = dateSelect.value;
            dateSelect.innerHTML = dates.map(d => `<option value="${d}">${d}</option>`).join('');

            if (dates.includes(currentVal)) {
                dateSelect.value = currentVal;
            } else if (dates.length > 0) {
                dateSelect.value = dates[0];
            }
        } catch (error) {
            console.error('Failed to update ceiling dates:', error);
        }
    },

    /**
     * 특정 날짜의 데이터를 로드하고 테이블을 렌더링합니다.
     * @async
     * @param {boolean} [forceSync=false] - 강제 동기화 여부
     */
    async loadData(forceSync = false) {
        const tableWrapper = document.getElementById('ceiling-table-container');
        const dateSelect = document.getElementById('ceiling-date');
        const date = dateSelect.value;

        if (!date) {
            tableWrapper.innerHTML = '<div class="stats-empty">데이터가 없습니다.</div>';
            return;
        }

        const refreshBtn = document.getElementById('ceiling-refresh');
        const icon = refreshBtn.querySelector('i');
        
        try {
            refreshBtn.disabled = true;
            icon.classList.add('fa-spin');
            tableWrapper.innerHTML = '<div class="stats-loader"><i class="fas fa-spinner fa-spin"></i> 구글 드라이브에서 데이터를 동기화 중입니다...</div>';

            const report = await statisticsService.getCeilingReport(date, forceSync);
            
            // 만약 새로 동기화했다면 날짜 목록을 한 번 더 갱신 (새로운 파일이 생겼을 수 있음)
            if (forceSync) await this.updateDateList();
            
            this.renderTable(report);
        } catch (error) {
            tableWrapper.innerHTML = `<div class="stats-error">오류 발생: ${error.message}</div>`;
        } finally {
            refreshBtn.disabled = false;
            icon.classList.remove('fa-spin');
        }
    },

    /**
     * 상한가 분석 리포트 테이블을 렌더링합니다.
     * @param {Object} report - 리포트 데이터 객체
     */
    renderTable(report) {
        const container = document.getElementById('ceiling-table-container');
        if (!report || !report.items || report.items.length === 0) {
            container.innerHTML = '<div class="stats-empty">해당 날짜에 분석된 종목이 없습니다.</div>';
            return;
        }

        const HIGH_PRICE_CLASSES = {
            '역·신': 'hp-red',
            '역·근': 'hp-orange',
            '52·신': 'hp-yellow',
            '52·근': 'hp-lightgreen'
        };

        let html = `
            <div class="ceiling-report-info">
                <span class="report-title">${report.title}</span>
                <span class="report-period">${report.start_date} ~ ${report.end_date}</span>
                <span class="balance-badge ${report.is_fully_collected ? 'badge-completed' : 'badge-collecting'}">
                    ${report.is_fully_collected ? '분석 완료' : '수집 중'}
                </span>
            </div>
            <table class="stats-table ceiling-table">
                <thead>
                    <tr>
                        <th style="width: 50px;">순번</th>
                        <th style="width: 70px;">태그</th>
                        <th>종목명</th>
                        <th style="width: 320px;">10일 가격 추이 (D+1 ~ D+10)</th>
                        <th style="width: 100px;">현재등락률</th>
                        <th style="width: 90px;">상태</th>
                    </tr>
                </thead>
                <tbody>
        `;

        report.items.forEach((item, idx) => {
            // 태그 스타일 결정 (수급 순위표와 일관성 유지)
            const hasTag = !!item.entry_tag;
            const hpClassSuffix = HIGH_PRICE_CLASSES[item.entry_tag] || '';
            const tagClass = hasTag 
                ? (hpClassSuffix ? `badge-highprice ${hpClassSuffix}` : (item.entry_tag === '상' ? 'ceiling-tag tag-ceiling' : 'ceiling-tag tag-newhigh'))
                : 'no-tag';
            
            const changeClass = item.change_rate > 0 ? 'change-up' : (item.change_rate < 0 ? 'change-down' : 'change-none');
            const changeSign = item.change_rate > 0 ? '+' : '';

            // 가격 추이 시각화 (박스 형태 + 첫날 가격 숫자)
            const pricesHtml = this.renderPriceSequence(item.closing_prices);

            html += `
                <tr>
                    <td class="col-rank">${idx + 1}</td>
                    <td><span class="${tagClass}">${item.entry_tag || '-'}</span></td>
                    <td class="col-name">
                        <span class="stock-name-text stock-link" data-name="${item.name}">${item.name}</span>
                    </td>
                    <td>
                        <div class="price-sequence-wrapper">
                            <span class="first-price">${item.closing_prices.length > 0 ? item.closing_prices[0].toLocaleString() : '-'}</span>
                            <div class="price-sequence">
                                ${pricesHtml}
                            </div>
                        </div>
                    </td>
                    <td class="${changeClass} font-bold">${changeSign}${item.change_rate.toFixed(2)}%</td>
                    <td>
                        <span class="status-dot ${item.is_completed ? 'dot-done' : 'dot-active'}"></span>
                        <span class="status-text">${item.is_completed ? '완결' : (item.closing_prices.length + '일')}</span>
                    </td>
                </tr>
            `;
        });

        html += '</tbody></table>';
        container.innerHTML = html;

        this.bindEventsAfterRender(container);
    },

    /**
     * 10일치 가격 추이를 시각화합니다.
     * @private
     */
    renderPriceSequence(prices) {
        // 박스 10개를 생성 (데이터가 있으면 p-up/p-down, 없으면 empty)
        let html = '';
        for (let i = 0; i < 10; i++) {
            const p = prices[i];
            if (p !== undefined) {
                let diffClass = '';
                if (i > 0 && prices[i-1] !== undefined) {
                    diffClass = p > prices[i-1] ? 'p-up' : (p < prices[i-1] ? 'p-down' : '');
                }
                html += `<div class="price-box ${diffClass}" title="Day ${i+1}: ${p.toLocaleString()}원"></div>`;
            } else {
                html += `<div class="price-box empty" title="데이터 수집 전"></div>`;
            }
        }
        return html;
    },

    /**
     * 렌더링 후 이벤트를 바인딩합니다. (종목 상세 이동 등)
     * @private
     */
    bindEventsAfterRender(container) {
        container.querySelectorAll('.stock-link').forEach(el => {
            el.addEventListener('click', async (e) => {
                const stockName = e.currentTarget.dataset.name;
                // 기존 app.js에 구현된 로직과 유사하게 검색 서비스 호출 가능
                // 여기서는 간단히 window 객체를 통한 글로벌 검색 유도
                if (window._findStockByTicker) {
                    const found = window._findStockByTicker(stockName, window._currentBoardData);
                    if (found) {
                        window.location.href = `/stock/${found.ticker}`;
                        return;
                    }
                }
                
                // 검색 API 시도
                try {
                    const res = await fetch(`/api/stock/search?q=${encodeURIComponent(stockName)}`);
                    const data = await res.json();
                    if (data && data.length > 0) {
                        window.location.href = `/stock/${data[0].ticker}`;
                    } else {
                        alert(`종목 [${stockName}]의 정보를 찾을 수 없습니다.`);
                    }
                } catch (err) {
                    console.error('Search failed:', err);
                }
            });
        });
    }
};
