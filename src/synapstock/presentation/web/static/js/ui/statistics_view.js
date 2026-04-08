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
                    <h2><i class="fas fa-chart-line"></i> 일별 수급 TOP 30</h2>
                    <div class="stats-filters">
                        <select id="stats-date" class="stats-select"></select>
                        <div class="stats-toggle-group">
                            <button class="stats-toggle active" data-market="KOSPI">KOSPI</button>
                            <button class="stats-toggle" data-market="KOSDAQ">KOSDAQ</button>
                        </div>
                        <div class="stats-toggle-group">
                            <button class="stats-toggle active" data-subject="FOREIGN">외국인</button>
                            <button class="stats-toggle" data-subject="INSTITUTION">기관</button>
                        </div>
                        <button id="stats-refresh" class="stats-btn-refresh"><i class="fas fa-sync-alt"></i></button>
                    </div>
                </div>
                <div id="stats-table-container" class="stats-table-wrapper">
                    <!-- 테이블이 여기에 렌더링됨 -->
                    <div class="stats-loader">데이터를 불러오는 중...</div>
                </div>
            </div>
        `;

        this.attachEvents();
    },

    /**
     * 이벤트 바인딩
     */
    attachEvents() {
        const dateSelect = document.getElementById('stats-date');
        const refreshBtn = document.getElementById('stats-refresh');
        const toggles = this.container.querySelectorAll('.stats-toggle');

        toggles.forEach(btn => {
            btn.addEventListener('click', async (e) => {
                // 부모 그룹 내의 다른 버튼 활성화 해제
                const group = e.target.closest('.stats-toggle-group');
                group.querySelectorAll('.stats-toggle').forEach(t => t.classList.remove('active'));
                e.target.classList.add('active');
                
                // 시장/주체가 바뀌면 날짜 목록도 다시 가져오는 것이 정확함
                if (e.target.dataset.market) await this.updateDateList();
                
                await this.loadData();
            });
        });

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

    /**
     * 선택된 시장/주체에 맞는 가용 날짜 목록 업데이트
     */
    async updateDateList() {
        const market = this.getSelectedMarket();
        const subject = this.getSelectedSubject();
        const dates = await statisticsService.getAvailableDates(market, subject);
        
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
        const market = this.getSelectedMarket();
        const subject = this.getSelectedSubject();

        if (!date) {
            tableWrapper.innerHTML = `
                <div class="stats-empty">
                    <div class="empty-content">
                        <i class="fas fa-folder-open"></i>
                        <p>가용한 상계 데이터가 없습니다.</p>
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
            const data = await statisticsService.getDailyRanking(date, market, subject);
            this.renderTable(data);
        } catch (error) {
            tableWrapper.innerHTML = `<div class="stats-error">오류 발생: ${error.message}</div>`;
        }
    },

    /**
     * 수급 순위표 테이블 렌더링
     */
    renderTable(data) {
        const container = document.getElementById('stats-table-container');
        if (!data || !data.items || data.items.length === 0) {
            container.innerHTML = '<div class="stats-empty">표시할 데이터가 없습니다.</div>';
            return;
        }

        let html = `
            <table class="stats-table">
                <thead>
                    <tr>
                        <th class="col-rank">순위</th>
                        <th class="col-change">변동</th>
                        <th class="col-name">종목명</th>
                        <th class="col-amount">순매수금액(백만)</th>
                        <th class="col-consecutive">연속 등장</th>
                    </tr>
                </thead>
                <tbody>
        `;

        data.items.forEach(item => {
            const changeHtml = this.getChangeIndicator(item);
            const consecutiveHtml = item.consecutive_days > 1 
                ? `<span class="badge-consecutive">${item.consecutive_days}일</span>`
                : '-';
                
            html += `
                <tr class="${item.is_new ? 'row-new' : ''}">
                    <td class="col-rank">${item.rank}</td>
                    <td class="col-change">${changeHtml}</td>
                    <td class="col-name"><strong>${item.name}</strong></td>
                    <td class="col-amount">${item.amount.toLocaleString()}</td>
                    <td class="col-consecutive">${consecutiveHtml}</td>
                </tr>
            `;
        });

        html += `</tbody></table>`;
        
        if (data.previous_date) {
            html += `<div class="stats-footer">※ 이전 거래일(${data.previous_date}) 대비 분석됨</div>`;
        }

        container.innerHTML = html;
    },

    /**
     * 순위 변동 표시용 HTML 생성
     */
    getChangeIndicator(item) {
        if (item.is_new) return '<span class="badge-new">NEW</span>';
        
        const change = item.rank_change;
        if (change > 0) {
            return `<span class="change-up"><i class="fas fa-caret-up"></i> ${change}</span>`;
        } else if (change < 0) {
            return `<span class="change-down"><i class="fas fa-caret-down"></i> ${Math.abs(change)}</span>`;
        } else {
            return '<span class="change-none">-</span>';
        }
    },

    getSelectedMarket() {
        return this.container.querySelector('[data-market].active').dataset.market;
    },

    getSelectedSubject() {
        return this.container.querySelector('[data-subject].active').dataset.subject;
    }
};
