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
        this.mainContainer = container;
        container.innerHTML = `
            <div class="stats-container animate-fade-in">
                <div class="stats-header">
                    <h2><i class="fas fa-rocket"></i> 유상증자 결정 공시 분석</h2>
                    <div class="stats-filters">
                        <select id="ci-year-select" class="stats-select" title="연도 선택">
                            <option value="2026">2026년</option>
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

            // 테이블 렌더링 (기본값: 전체 또는 현재 선택된 연도)
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

        // 기본값: 2026년 우선 선택, 없으면 최신 연도, 그마저도 없으면 기존 값
        if (years.includes("2026")) {
            yearSelect.value = "2026";
        } else if (currentValue && years.includes(currentValue)) {
            yearSelect.value = currentValue;
        } else if (years.length > 0) {
            yearSelect.value = years[0];
        }
    },

    /**
     * 필터링된 데이터를 단일 테이블에 렌더링합니다.
     */
    renderTable: function (items, selectedYear) {
        const tbody = document.getElementById('capital-increase-tbody');
        if (!tbody) return;

        if (!items || items.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="stats-empty">데이터가 없습니다.</td></tr>';
            return;
        }

        // 1. 데이터 필터링
        let filteredItems = items;
        if (selectedYear && selectedYear !== "all" && selectedYear !== "전체") {
            filteredItems = items.filter(item => {
                const date = item.disclosure_date || item.date;
                return date && date.startsWith(selectedYear);
            });
        }

        // 2. 렌더링 (단일 테이블 tbody 교체)
        tbody.innerHTML = '';
        filteredItems.forEach((item, idx) => {
            const total = (item.fund_facility || 0) + (item.fund_operation || 0) + (item.fund_acquisition || 0) + (item.fund_etc || 0);
            
            // 메인 행 (Basic Info)
            const tr = document.createElement('tr');
            tr.className = 'ci-row';
            tr.style.cursor = 'pointer';
            tr.innerHTML = `
                <td style="color:#9ca3af;">${item.disclosure_date || item.date}</td>
                <td style="font-weight:600; color:#e5e7eb;">
                    ${item.ticker ? `<a href="/stock/${item.ticker}" onclick="event.stopPropagation(); event.preventDefault(); window._jumpToStock('${item.ticker}', '${item.name}')" style="color:inherit; text-decoration:none;">${item.name}</a>` : item.name}
                    ${item.is_correction ? '<span style="font-size:0.75rem; background:#ef4444; color:white; padding:1px 4px; border-radius:3px; margin-left:5px;">기재정정</span>' : ''}
                </td>
                <td style="color:#60a5fa;">${item.method}</td>
                <td style="text-align:right; font-weight:600; color:#facc15;">${this.formatUnit(total)}</td>
                <td style="text-align:right; color:#e5e7eb;">${item.issue_price ? item.issue_price.toLocaleString() : '-'}</td>
                <td style="text-align:right; color:#9ca3af;">${item.payment_date || '-'}</td>
                <td style="text-align:center;">
                    <span class="expand-icon" style="color:var(--accent-blue); display: inline-block; transition: transform 0.2s;">▼</span>
                </td>
            `;

            // 상세 행 (Detail - 초기에는 숨김 및 비어있음)
            const detailTr = document.createElement('tr');
            detailTr.className = 'detail-row';
            detailTr.style.display = 'none';
            detailTr.innerHTML = `<td colspan="7" class="detail-container"></td>`;

            tbody.appendChild(tr);
            tbody.appendChild(detailTr);

            // 3. 행 클릭 이벤트 (지능형 지연 로딩)
            tr.onclick = (e) => {
                const link = e.target.closest('a');
                if (link) return;

                const container = detailTr.querySelector('.detail-container');
                const icon = tr.querySelector('.expand-icon');
                const isHidden = detailTr.style.display === 'none';

                if (isHidden) {
                    // [추가] 다른 열린 상세 행들을 모두 닫음 (Focus Mode)
                    tbody.querySelectorAll('.detail-row').forEach(row => {
                        row.style.display = 'none';
                    });
                    tbody.querySelectorAll('.expand-icon').forEach(ic => {
                        ic.style.transform = 'rotate(0deg)';
                    });

                    // 펼칠 때 내용이 없으면 그때 생성 (성능 최적화)
                    if (container.innerHTML.trim().length < 50) {
                        container.innerHTML = this.generateDetailHtml(item, total);
                    }
                    detailTr.style.display = 'table-row';
                    if (icon) icon.style.transform = 'rotate(180deg)';
                } else {
                    detailTr.style.display = 'none';
                    if (icon) icon.style.transform = 'rotate(0deg)';
                }
            };
        });
    },

    /**
     * 상세 보기를 위한 HTML 조각을 생성합니다.
     */
    generateDetailHtml: function (item, totalAmount) {
        const p = (val) => totalAmount > 0 ? (val / totalAmount * 100).toFixed(1) : 0;

        return `
            <div class="ci-detail-container">
                <div class="ci-detail-grid">
                    <!-- 자금 조달 목적 분석 -->
                    <div class="ci-card">
                        <h4><i class="fas fa-chart-pie"></i> 자금 조달 목적 비중</h4>
                        <div class="fund-item">
                            <div class="fund-label-row">
                                <span>시설 자금</span>
                                <span>${this.formatUnit(item.fund_facility)} (${p(item.fund_facility)}%)</span>
                            </div>
                            <div class="fund-progress-bg">
                                <div class="fund-progress-bar" style="width: ${p(item.fund_facility)}%;"></div>
                            </div>
                        </div>
                        <div class="fund-item">
                            <div class="fund-label-row">
                                <span>운영 자금</span>
                                <span>${this.formatUnit(item.fund_operation)} (${p(item.fund_operation)}%)</span>
                            </div>
                            <div class="fund-progress-bg">
                                <div class="fund-progress-bar" style="width: ${p(item.fund_operation)}%; opacity: 0.8;"></div>
                            </div>
                        </div>
                        <div class="fund-item">
                            <div class="fund-label-row">
                                <span>타법인 증권 취득</span>
                                <span>${this.formatUnit(item.fund_acquisition)} (${p(item.fund_acquisition)}%)</span>
                            </div>
                            <div class="fund-progress-bg">
                                <div class="fund-progress-bar" style="width: ${p(item.fund_acquisition)}%; opacity: 0.6;"></div>
                            </div>
                        </div>
                        <div class="fund-item">
                            <div class="fund-label-row">
                                <span>기타 자금</span>
                                <span>${this.formatUnit(item.fund_etc)} (${p(item.fund_etc)}%)</span>
                            </div>
                            <div class="fund-progress-bg">
                                <div class="fund-progress-bar" style="width: ${p(item.fund_etc)}%; opacity: 0.4;"></div>
                            </div>
                        </div>
                    </div>

                    <!-- 주요 일정 타임라인 -->
                    <div class="ci-card">
                        <h4><i class="fas fa-calendar-alt"></i> 주요 일정</h4>
                        <div class="timeline">
                            <div class="timeline-item ${item.disclosure_date ? 'active' : ''}">
                                <div class="timeline-label">공시일</div>
                                <div class="timeline-date">${item.disclosure_date || '-'}</div>
                            </div>
                            <div class="timeline-item ${item.record_date ? 'active' : ''}">
                                <div class="timeline-label">신주배정기준일</div>
                                <div class="timeline-date">${item.record_date || '-'}</div>
                            </div>
                            <div class="timeline-item ${item.subscription_date ? 'active' : ''}">
                                <div class="timeline-label">청약예정일</div>
                                <div class="timeline-date">${item.subscription_date || '-'}</div>
                            </div>
                            <div class="timeline-item ${item.payment_date ? 'active' : ''}">
                                <div class="timeline-label">납입일</div>
                                <div class="timeline-date">${item.payment_date || '-'}</div>
                            </div>
                            <div class="timeline-item ${item.listing_date ? 'active' : ''}">
                                <div class="timeline-label">신주상장일</div>
                                <div class="timeline-date">${item.listing_date || '-'}</div>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="ci-info-footer">
                    <div style="margin-right: auto; font-size: 0.85rem; color: #9ca3af;">
                        <span style="margin-right: 15px;">신주발행: <b>${item.new_shares ? item.new_shares.toLocaleString() : '-'}</b> 주</span>
                        <span>발행가: <b>${item.issue_price ? item.issue_price.toLocaleString() : '-'}</b> 원</span>
                    </div>
                    <a href="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${item.rcp_no}" target="_blank" class="ci-btn-action ci-btn-dart">
                        DART 공시 원문 보기 <i class="fas fa-external-link-alt"></i>
                    </a>
                </div>
            </div>
        `;
    },

    /**
     * 큰 금액을 읽기 쉬운 단위(억 등)로 포맷팅합니다.
     */
    formatUnit: function (value) {
        if (!value || value === 0) return '0';
        if (value >= 100000000) {
            return `${(value / 100000000).toFixed(1)}억`;
        } else if (value >= 10000) {
            return `${(value / 10000).toFixed(0)}만`;
        }
        return value.toLocaleString();
    }
};

