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
    render: async function (container) {
        container.innerHTML = `
            <div class="stats-container animate-fade-in">
                <div class="stats-header">
                    <h2><i class="fas fa-rocket"></i> 유상증자 결정 공시 분석</h2>
                    <div class="stats-filters">
                        <select id="ci-year-select" class="stats-select" title="연도 선택">
                            <option value="all">전체 연도</option>
                        </select>
                        <button id="sync-capital-increase-btn" class="stats-btn-refresh" title="최신 데이터 동기화">
                            <i class="fas fa-sync-alt"></i>
                        </button>
                    </div>
                </div>
                
                <div class="stats-table-wrapper">
                    <table class="stats-table" id="capital-increase-table">
                        <thead>
                            <tr>
                                <th style="width: 140px;">공시일</th>
                                <th>종목명</th>
                                <th style="width: 240px;">증자방식</th>
                                <th style="width: 110px; text-align:right;">조달금액</th>
                                <th style="width: 110px; text-align:right;">발행가액</th>
                                <th style="width: 140px; text-align:right;">납입일</th>
                                <th style="width: 70px; text-align:center;">이동</th>
                            </tr>
                        </thead>
                        <tbody id="capital-increase-tbody">
                            <tr><td colspan="7" class="stats-loader">데이터를 불러오는 중...</td></tr>
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
    initEventListeners: function () {
        // 동기화 버튼
        const syncBtn = document.getElementById('sync-capital-increase-btn');
        if (syncBtn) {
            syncBtn.onclick = async () => {
                const icon = syncBtn.querySelector('i');
                syncBtn.disabled = true;
                if (icon) icon.classList.add('fa-spin');
                await this.loadData(true);
                syncBtn.disabled = false;
                if (icon) icon.classList.remove('fa-spin');
            };
        }

        // 연도 필터 드롭다운
        const yearSelect = document.getElementById('ci-year-select');
        if (yearSelect) {
            yearSelect.onchange = () => {
                this.renderTable(this.cachedItems, yearSelect.value);
            };
        }
    },

    /**
     * 전체 유상증자 데이터를 보관하는 내부 캐시
     */
    cachedItems: [],

    /**
     * 서버로부터 유상증자 데이터를 가져옵니다.
     * @param {boolean} forceSync - 강제 동기화 여부
     */
    loadData: async function (forceSync = false) {
        try {
            const response = await fetch(`/api/statistics/capital-increase?force_sync=${forceSync}`);
            const data = await response.json();
            const items = data.items || [];

            // 최신순 정렬 (내림차순)
            items.sort((a, b) => {
                const dateA = a.disclosure_date || a.date || "";
                const dateB = b.disclosure_date || b.date || "";
                return dateB.localeCompare(dateA);
            });

            this.cachedItems = items;

            // 연도 드롭다운 업데이트
            this.updateYearOptions(items);

            // 테이블 렌더링 (기본값: 전체)
            const yearSelect = document.getElementById('ci-year-select');
            this.renderTable(items, yearSelect ? yearSelect.value : 'all');

        } catch (err) {
            console.error('Failed to load capital increase data:', err);
            const tbody = document.getElementById('capital-increase-tbody');
            if (tbody) tbody.innerHTML = `<tr><td colspan="7" class="stats-error">데이터 로드 실패: ${err.message}</td></tr>`;
        }
    },

    /**
     * 데이터에서 연도를 추출하여 드롭다운 메뉴를 구성합니다.
     */
    updateYearOptions: function (items) {
        const yearSelect = document.getElementById('ci-year-select');
        if (!yearSelect) return;

        // "전체 연도" 옵션 유지
        const currentValue = yearSelect.value;
        yearSelect.innerHTML = '<option value="all">전체 연도</option>';

        // 고유 연도 추출 및 내림차순 정렬
        const years = [...new Set(items.map(item => {
            const d = item.disclosure_date || item.date || "";
            return d.substring(0, 4);
        }))].filter(y => y && y.length === 4).sort((a, b) => b.localeCompare(a));

        years.forEach(year => {
            const option = document.createElement('option');
            option.value = year;
            option.textContent = `${year}년`;
            yearSelect.appendChild(option);
        });

        // 기존 선택값 유지 시도
        if (currentValue && years.includes(currentValue)) {
            yearSelect.value = currentValue;
        }
    },

    /**
     * 필터링된 데이터를 테이블에 렌더링합니다.
     */
    renderTable: function (items, selectedYear) {
        const tbody = document.getElementById('capital-increase-tbody');
        if (!tbody) return;

        const filteredItems = selectedYear === 'all'
            ? items
            : items.filter(item => {
                const d = item.disclosure_date || item.date || "";
                return d.startsWith(selectedYear);
            });

        if (filteredItems.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="stats-empty">조건에 맞는 데이터가 없습니다.</td></tr>';
            return;
        }

        tbody.innerHTML = filteredItems.map(item => {
            const totalAmount = (item.fund_facility || 0) + (item.fund_operation || 0) + (item.fund_acquisition || 0) + (item.fund_etc || 0);

            return `
                <tr style="cursor:pointer;" class="ci-row" data-id="${item.rcp_no}">
                    <td style="color:#9ca3af;">${item.disclosure_date || item.date}</td>
                    <td style="font-weight:600; color:#e5e7eb;">
                        ${item.ticker ? `<a href="/stock/${item.ticker}" onclick="event.stopPropagation(); event.preventDefault(); window._jumpToStock('${item.ticker}', '${item.name}')" style="color:inherit; text-decoration:none;">${item.name}</a>` : item.name}
                        ${item.is_correction ? '<span style="font-size:0.75rem; background:#ef4444; color:white; padding:1px 4px; border-radius:3px; margin-left:5px;">기재정정</span>' : ''}
                    </td>
                    <td style="color:#60a5fa;">${item.method}</td>
                    <td style="text-align:right; font-weight:600; color:#facc15;">${this.formatUnit(totalAmount)}</td>
                    <td style="text-align:right; color:#e5e7eb;">${item.issue_price ? item.issue_price.toLocaleString() : '-'}</td>
                    <td style="text-align:right; color:#9ca3af;">${item.payment_date || '-'}</td>
                    <td style="text-align:center;">
                        <a href="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${item.rcp_no}" target="_blank" onclick="event.stopPropagation();" 
                           style="color:#facc15; text-decoration:none; border: 1px solid #facc15; padding: 2px 10px; border-radius: 4px; font-size: 0.9rem; background: rgba(250,204,21,0.05); transition: background 0.2s;"
                           onmouseover="this.style.background='rgba(250,204,21,0.2)'"
                           onmouseout="this.style.background='rgba(250,204,21,0.05)'"
                           title="DART 공시 원문 보기">
                            📄
                        </a>
                    </td>
                </tr>
            `;
        }).join('');

        // 행 클릭 이벤트 바인딩 (상세 정보용)
        tbody.querySelectorAll('.ci-row').forEach(row => {
            row.onclick = () => {
                const id = row.dataset.id;
                console.log('Show detail for:', id);
                // TODO: 상세 모달 구현 시 연결
                if (window.showCapitalIncreaseDetail) {
                    window.showCapitalIncreaseDetail(id);
                }
            };
        });
    },

    /**
     * 큰 금액을 읽기 쉬운 단위(억 등)로 포맷팅합니다.
     */
    formatUnit: function (value) {
        if (value >= 100000000) {
            return `${(value / 100000000).toFixed(1)}억`;
        } else if (value >= 10000) {
            return `${(value / 10000).toFixed(0)}만`;
        }
        return value.toLocaleString();
    }
};
