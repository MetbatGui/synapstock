/**
 * @fileoverview 유상증자(Capital Increase) 분석 뷰 모듈.
 * 
 * 구글 드라이브에서 동기화된 유상증자 결심 공시 데이터를 테이블 형식으로 표시하고
 * 자금 조달 목적 및 증자 방식을 요약하여 보여줍니다.
 */

export const capitalIncreaseView = {
    /**
     * 유상증자 분석 뷰를 렌더링합니다.
     * @param {HTMLElement} container - 렌더링될 대상 컨테이너.
     */
    render: async function(container) {
        container.innerHTML = `
            <div class="stats-header" style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;">
                <h2 style="margin:0; color:#facc15;">🚀 유상증자 결정 공시 분석</h2>
                <button id="sync-capital-increase-btn" class="btn btn-secondary btn-sm" style="background:rgba(250,204,21,0.1); border:1px solid #facc15; color:#facc15;">
                    <i class="fas fa-sync-alt"></i> 최신 데이터 동기화
                </button>
            </div>
            <div id="capital-increase-summary" class="stats-summary-grid" style="display:grid; grid-template-columns: repeat(4, 1fr); gap:15px; margin-bottom:25px;">
                <div class="card stat-mini-box" style="padding:15px; text-align:center;">
                    <div class="label" style="font-size:0.85rem; color:#9ca3af; margin-bottom:5px;">총 공시 건수</div>
                    <div class="value" id="ci-total-count" style="font-size:1.5rem; font-weight:700; color:#e5e7eb;">--</div>
                </div>
                <div class="card stat-mini-box" style="padding:15px; text-align:center;">
                    <div class="label" style="font-size:0.85rem; color:#9ca3af; margin-bottom:5px;">시설자금 합계</div>
                    <div class="value" id="ci-total-facility" style="font-size:1.5rem; font-weight:700; color:#3b82f6;">--</div>
                </div>
                <div class="card stat-mini-box" style="padding:15px; text-align:center;">
                    <div class="label" style="font-size:0.85rem; color:#9ca3af; margin-bottom:5px;">운영자금 합계</div>
                    <div class="value" id="ci-total-operation" style="font-size:1.5rem; font-weight:700; color:#10b981;">--</div>
                </div>
                <div class="card stat-mini-box" style="padding:15px; text-align:center;">
                    <div class="label" style="font-size:0.85rem; color:#9ca3af; margin-bottom:5px;">타법인 취득 합계</div>
                    <div class="value" id="ci-total-acquisition" style="font-size:1.5rem; font-weight:700; color:#f59e0b;">--</div>
                </div>
            </div>
            <div class="card stats-table-card" style="padding:0; overflow:hidden;">
                <div class="table-scroll-wrapper" style="overflow-x:auto;">
                    <table class="stats-table" id="capital-increase-table" style="width:100%; border-collapse:collapse; font-size:0.9rem;">
                        <thead style="background:rgba(255,255,255,0.05); border-bottom:1px solid rgba(255,255,255,0.1);">
                            <tr>
                                <th style="padding:12px; text-align:left;">공시일</th>
                                <th style="padding:12px; text-align:left;">종목명</th>
                                <th style="padding:12px; text-align:left;">증자방식</th>
                                <th style="padding:12px; text-align:right;">시설자금</th>
                                <th style="padding:12px; text-align:right;">운영자금</th>
                                <th style="padding:12px; text-align:right;">타법인취득</th>
                                <th style="padding:12px; text-align:right;">신주배정일</th>
                                <th style="padding:12px; text-align:center;">상세</th>
                            </tr>
                        </thead>
                        <tbody id="capital-increase-tbody">
                            <tr><td colspan="8" style="padding:40px; text-align:center; color:#9ca3af;">데이터를 불러오는 중...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>
        `;

        this.initEventListeners();
        await this.loadData();
    },

    /**
     * 이벤트 리스너를 등록합니다.
     */
    initEventListeners: function() {
        const syncBtn = document.getElementById('sync-capital-increase-btn');
        if (syncBtn) {
            syncBtn.onclick = async () => {
                syncBtn.disabled = true;
                syncBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 동기화 중...';
                await this.loadData(true);
                syncBtn.disabled = false;
                syncBtn.innerHTML = '<i class="fas fa-sync-alt"></i> 최신 데이터 동기화';
            };
        }
    },

    /**
     * 서버로부터 유상증자 데이터를 가져와 렌더링합니다.
     * @param {boolean} forceSync - 강제 동기화 여부
     */
    loadData: async function(forceSync = false) {
        const tbody = document.getElementById('capital-increase-tbody');
        try {
            const response = await fetch(`/api/statistics/capital-increase?force_sync=${forceSync}`);
            const data = await response.json();
            const items = data.items || [];

            if (items.length === 0) {
                tbody.innerHTML = '<tr><td colspan="8" style="padding:40px; text-align:center; color:#9ca3af;">데이터가 없습니다. 구글 드라이브 설정을 확인해 주세요.</td></tr>';
                return;
            }

            // 요약 정보 업데이트
            this.updateSummary(items);

            // 테이블 렌더링
            tbody.innerHTML = items.map(item => `
                <tr style="border-bottom:1px solid rgba(255,255,255,0.03); transition:background 0.2s;" onmouseover="this.style.background='rgba(255,255,255,0.02)'" onmouseout="this.style.background='transparent'">
                    <td style="padding:12px; color:#9ca3af;">${item.disclosure_date || item.date}</td>
                    <td style="padding:12px; font-weight:600; color:#e5e7eb;">
                        ${item.ticker ? `<a href="/stock/${item.ticker}" onclick="event.preventDefault(); window._jumpToStock('${item.ticker}', '${item.name}')" style="color:inherit; text-decoration:none;">${item.name}</a>` : item.name}
                        ${item.is_correction ? '<span style="font-size:0.75rem; background:#ef4444; color:white; padding:1px 4px; border-radius:3px; margin-left:5px;">정정</span>' : ''}
                    </td>
                    <td style="padding:12px; color:#60a5fa;">${item.method}</td>
                    <td style="padding:12px; text-align:right; color:#3b82f6;">${item.fund_facility.toLocaleString()}</td>
                    <td style="padding:12px; text-align:right; color:#10b981;">${item.fund_operation.toLocaleString()}</td>
                    <td style="padding:12px; text-align:right; color:#f59e0b;">${item.fund_acquisition.toLocaleString()}</td>
                    <td style="padding:12px; color:#9ca3af;">${item.record_date || '-'}</td>
                    <td style="padding:12px; text-align:center;">
                        <a href="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${item.rcp_no}" target="_blank" style="color:#facc15; text-decoration:none; font-size:1.1rem;" title="DART 공시 보기">
                            <i class="fas fa-external-link-alt"></i>
                        </a>
                    </td>
                </tr>
            `).join('');

        } catch (err) {
            console.error('Failed to load capital increase data:', err);
            tbody.innerHTML = `<tr><td colspan="8" style="padding:40px; text-align:center; color:#ef4444;">데이터 로드 실패: ${err.message}</td></tr>`;
        }
    },

    /**
     * 상단 요약 카드의 수치를 업데이트합니다.
     */
    updateSummary: function(items) {
        const totalCount = items.length;
        const totalFacility = items.reduce((sum, item) => sum + (item.fund_facility || 0), 0);
        const totalOperation = items.reduce((sum, item) => sum + (item.fund_operation || 0), 0);
        const totalAcquisition = items.reduce((sum, item) => sum + (item.fund_acquisition || 0), 0);

        const countEl = document.getElementById('ci-total-count');
        const facilityEl = document.getElementById('ci-total-facility');
        const operationEl = document.getElementById('ci-total-operation');
        const acquisitionEl = document.getElementById('ci-total-acquisition');

        if (countEl) countEl.innerText = `${totalCount}건`;
        if (facilityEl) facilityEl.innerText = this.formatUnit(totalFacility);
        if (operationEl) operationEl.innerText = this.formatUnit(totalOperation);
        if (acquisitionEl) acquisitionEl.innerText = this.formatUnit(totalAcquisition);
    },

    /**
     * 큰 금액을 읽기 쉬운 단위(억 등)로 포맷팅합니다.
     */
    formatUnit: function(value) {
        if (value >= 100000000) {
            return `${(value / 100000000).toFixed(1)}억`;
        } else if (value >= 10000) {
            return `${(value / 10000).toFixed(0)}만`;
        }
        return value.toLocaleString();
    }
};
