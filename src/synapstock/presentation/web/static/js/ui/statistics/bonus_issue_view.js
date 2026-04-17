/**
 * @fileoverview 무상증자(Bonus Issue) 분석 뷰 모듈.
 * 
 * 구글 드라이브에서 동기화된 무상증자 결정 공시 데이터를 테이블 형식으로 표시하고
 * 배정 비율, 기준일, 상장일 등의 핵심 일정을 관리합니다.
 */

export const bonusIssueView = {
    /**
     * 무상증자 분석 뷰를 렌더링합니다.
     * @param {HTMLElement} container - 렌더링될 대상 컨테이너.
     */
    render: async function (container) {
        this.mainContainer = container;
        container.innerHTML = `
            <div class="stats-container animate-fade-in">
                <div class="stats-header">
                    <h2><i class="fas fa-gift"></i> 무상증자 결정 공시 분석</h2>
                    <div class="stats-filters">
                        <select id="bi-year-select" class="stats-select" title="연도 선택">
                            <option value="2026">2026년</option>
                            <option value="all">전체 연도</option>
                        </select>
                        <button id="sync-bonus-issue-btn" class="stats-btn-refresh" title="최신 데이터 동기화">
                            <i class="fas fa-sync-alt"></i>
                        </button>
                    </div>
                </div>
                
                <div class="stats-table-wrapper">
                    <table class="stats-table" id="bonus-issue-table">
                        <thead>
                            <tr>
                                <th style="width: 140px;">공시일</th>
                                <th>종목명</th>
                                <th style="width: 120px; text-align:right;">배정비율</th>
                                <th style="width: 180px; text-align:right;">신주 발행수</th>
                                <th style="width: 140px; text-align:right;">배정기준일</th>
                                <th style="width: 140px; text-align:right;">상장예정일</th>
                                <th style="width: 70px; text-align:center;">상세</th>
                            </tr>
                        </thead>
                        <tbody id="bonus-issue-tbody">
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
        const syncBtn = document.getElementById('sync-bonus-issue-btn');
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

        const yearSelect = document.getElementById('bi-year-select');
        if (yearSelect) {
            yearSelect.onchange = () => {
                this.renderTable(this.cachedItems, yearSelect.value);
            };
        }
    },

    cachedItems: [],

    /**
     * 서버로부터 무상증자 데이터를 가져옵니다.
     * @param {boolean} forceSync - 강제 동기화 여부
     */
    loadData: async function (forceSync = false) {
        try {
            const response = await fetch(`/api/statistics/bonus-issue?force_sync=${forceSync}`);
            const data = await response.json();
            const items = data.items || [];

            // 최신순 정렬
            items.sort((a, b) => {
                const dateA = a.disclosure_date || a.date || "";
                const dateB = b.disclosure_date || b.date || "";
                return dateB.localeCompare(dateA);
            });

            this.cachedItems = this.calculateCorrectionOrders(items);
            this.updateYearOptions(items);

            const yearSelect = document.getElementById('bi-year-select');
            this.renderTable(this.cachedItems, yearSelect ? yearSelect.value : 'all');

        } catch (err) {
            console.error('Failed to load bonus issue data:', err);
            const tbody = document.getElementById('bonus-issue-tbody');
            if (tbody) tbody.innerHTML = `<tr><td colspan="7" class="stats-error">데이터 로드 실패: ${err.message}</td></tr>`;
        }
    },

    updateYearOptions: function (items) {
        const yearSelect = document.getElementById('bi-year-select');
        if (!yearSelect) return;

        const currentValue = yearSelect.value;
        yearSelect.innerHTML = '<option value="all">전체 연도</option>';

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

        if (years.includes("2026")) {
            yearSelect.value = "2026";
        } else if (currentValue && years.includes(currentValue)) {
            yearSelect.value = currentValue;
        } else if (years.length > 0) {
            yearSelect.value = years[0];
        }
    },

    renderTable: function (items, selectedYear) {
        const tbody = document.getElementById('bonus-issue-tbody');
        if (!tbody) return;

        if (!items || items.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="stats-empty">데이터가 없습니다.</td></tr>';
            return;
        }

        let filteredItems = items;
        if (selectedYear && selectedYear !== "all") {
            filteredItems = items.filter(item => {
                const date = item.disclosure_date || item.date;
                return date && date.startsWith(selectedYear);
            });
        }

        tbody.innerHTML = '';
        filteredItems.forEach((item) => {
            const tr = document.createElement('tr');
            tr.className = 'bi-row';
            tr.dataset.rcpNo = item.rcp_no;
            tr.style.cursor = 'pointer';
            
            const ratioPercent = (item.shares_per_old * 100).toFixed(0);

            tr.innerHTML = `
                <td style="color:#9ca3af;">${item.disclosure_date || item.date}</td>
                <td style="font-weight:600; color:#e5e7eb;">
                    ${item.ticker ? `<a href="/stock/${item.ticker}" onclick="event.stopPropagation(); event.preventDefault(); window._jumpToStock('${item.ticker}', '${item.name}')" style="color:inherit; text-decoration:none;">${item.name}</a>` : item.name}
                    ${item.is_correction ? `<span style="font-size:0.75rem; background:#ef4444; color:white; padding:1px 4px; border-radius:3px; margin-left:5px;">기재정정${item.correction_count > 0 ? ` (${item.correction_count}차)` : ''}</span>` : ''}
                </td>
                <td style="text-align:right; font-weight:700; color:#4ade80;">1 : ${item.shares_per_old} (${ratioPercent}%)</td>
                <td style="text-align:right; color:#e5e7eb;">${item.new_shares ? item.new_shares.toLocaleString() : '-'}</td>
                <td style="text-align:right; color:#9ca3af;">${item.record_date || '-'}</td>
                <td style="text-align:right; color:#facc15;">${item.listing_date || '-'}</td>
                <td style="text-align:center;">
                    <span class="expand-icon" style="color:var(--accent-blue); display: inline-block; transition: transform 0.2s;">▼</span>
                </td>
            `;

            const detailTr = document.createElement('tr');
            detailTr.className = 'detail-row';
            detailTr.style.display = 'none';
            detailTr.innerHTML = `<td colspan="7" class="detail-container"></td>`;

            tbody.appendChild(tr);
            tbody.appendChild(detailTr);

            tr.onclick = (e) => {
                if (e.target.closest('a')) return;

                const container = detailTr.querySelector('.detail-container');
                const icon = tr.querySelector('.expand-icon');
                const isHidden = detailTr.style.display === 'none';

                if (isHidden) {
                    tbody.querySelectorAll('.detail-row').forEach(row => row.style.display = 'none');
                    tbody.querySelectorAll('.expand-icon').forEach(ic => ic.style.transform = 'rotate(0deg)');

                    if (container.innerHTML.trim().length < 50) {
                        container.innerHTML = this.generateDetailHtml(item);
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

    generateDetailHtml: function (item) {
        return `
            <div class="ci-detail-container animate-fade-in" style="background: rgba(255,255,255,0.02); border-radius: 8px; padding: 20px;">
                <div class="ci-detail-grid" style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 20px;">
                    <!-- 정보 카드 1: 증자 개요 -->
                    <div class="ci-card" style="background: rgba(0,0,0,0.2); padding: 15px; border-radius: 8px;">
                        <h4 style="margin-top:0; color:var(--accent-primary); border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 8px; margin-bottom: 12px;">
                            <i class="fas fa-info-circle"></i> 증자 개요
                        </h4>
                        <div style="display: flex; flex-direction: column; gap: 10px;">
                            <div style="display: flex; justify-content: space-between;">
                                <span style="color: #9ca3af;">신주배정비율</span>
                                <span style="font-weight: 700; color: #4ade80;">1주당 ${item.shares_per_old}주</span>
                            </div>
                            <div style="display: flex; justify-content: space-between;">
                                <span style="color: #9ca3af;">신주발행주식수</span>
                                <span style="font-weight: 700;">${item.new_shares ? item.new_shares.toLocaleString() : '-'} 주</span>
                            </div>
                            <div style="display: flex; justify-content: space-between; flex-direction: column; margin-top: 8px;">
                                <span style="color: #9ca3af; margin-bottom: 4px;">무상증자 재원</span>
                                <span style="font-weight: 600; color: #60a5fa;">${item.capital_reserve || '정보 없음'}</span>
                            </div>
                        </div>
                    </div>

                    <!-- 정보 카드 2: 주요 일정 -->
                    <div class="ci-card" style="background: rgba(0,0,0,0.2); padding: 15px; border-radius: 8px;">
                        <h4 style="margin-top:0; color:var(--accent-primary); border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 8px; margin-bottom: 12px;">
                            <i class="fas fa-calendar-alt"></i> 주요 일정
                        </h4>
                        <div class="timeline" style="display: flex; flex-direction: column; gap: 8px;">
                            <div style="display: flex; justify-content: space-between;">
                                <span style="color: #9ca3af;">배정기준일</span>
                                <span style="font-weight: 600;">${item.record_date || '-'}</span>
                            </div>
                            <div style="display: flex; justify-content: space-between;">
                                <span style="color: #9ca3af;">상장예정일</span>
                                <span style="font-weight: 600; color: #facc15;">${item.listing_date || '-'}</span>
                            </div>
                            <div style="display: flex; justify-content: space-between;">
                                <span style="color: #9ca3af;">공시일</span>
                                <span style="font-weight: 600;">${item.disclosure_date || '-'}</span>
                            </div>
                        </div>
                    </div>

                    <!-- 정보 카드 3: 링크 및 액션 -->
                    <div class="ci-card" style="background: rgba(0,0,0,0.2); padding: 15px; border-radius: 8px; display: flex; flex-direction: column; justify-content: space-between;">
                        <h4 style="margin-top:0; color:var(--accent-primary); border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 8px; margin-bottom: 12px;">
                            <i class="fas fa-link"></i> 바로가기
                        </h4>
                        <div style="display: flex; flex-direction: column; gap: 10px;">
                            <a href="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${item.rcp_no}" target="_blank" class="stats-btn-refresh" style="text-decoration:none; display:flex; align-items:center; justify-content:center; gap:8px; padding: 10px; width:100%; box-sizing:border-box;">
                                DART 공시 원문 <i class="fas fa-external-link-alt"></i>
                            </a>
                            <button onclick="window._jumpToStock('${item.ticker}', '${item.name}')" class="stats-btn-refresh" style="background: rgba(96, 165, 250, 0.1); color: #60a5fa; border: 1px solid rgba(96, 165, 250, 0.3); padding: 10px; border-radius: 6px; cursor: pointer;">
                                <i class="fas fa-search-dollar"></i> 종목 분석으로 이동
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
    },

    calculateCorrectionOrders: function (items) {
        if (!items || items.length === 0) return [];
        const itemMap = {};
        items.forEach(item => { if (item.rcp_no) itemMap[item.rcp_no] = item; });

        return items.map(item => {
            let count = 0;
            let current = item;
            while (current && current.parent_rcp_no && itemMap[current.parent_rcp_no]) {
                count++;
                current = itemMap[current.parent_rcp_no];
                if (current.rcp_no === item.rcp_no) break;
            }
            return { ...item, correction_count: count };
        });
    }
};
