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
            <div class="stats-container stats-narrow animate-fade-in">
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
            
            const ratioVal = (item.shares_per_old && item.shares_per_old > 0) ? item.shares_per_old.toFixed(2) : '-';
            const ratioPercent = (item.shares_per_old && item.shares_per_old > 0) ? (item.shares_per_old * 100).toFixed(2) : '-';

            tr.innerHTML = `
                <td style="color:#9ca3af;">${item.disclosure_date || item.date}</td>
                <td style="font-weight:600; color:#e5e7eb;">
                    ${item.ticker ? `<a href="/stock/${item.ticker}" onclick="event.stopPropagation(); event.preventDefault(); window._jumpToStock('${item.ticker}', '${item.name}')" style="color:inherit; text-decoration:none;">${item.name}</a>` : item.name}
                    ${item.is_correction ? `<span style="font-size:0.75rem; background:#ef4444; color:white; padding:1px 4px; border-radius:3px; margin-left:5px;">기재정정 ${item.correction_count > 0 ? `+${item.correction_count}` : ''}</span>` : ''}
                </td>
                <td style="text-align:right; font-weight:700; color:#4ade80;">1 : ${ratioVal} ${ratioPercent !== '-' ? `(${ratioPercent}%)` : ''}</td>
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
                    // 다른 열려있는 상세 행 닫기
                    tbody.querySelectorAll('.detail-row').forEach(row => row.classList.remove('expanded'));
                    tbody.querySelectorAll('.expand-icon').forEach(ic => ic.style.transform = 'rotate(0deg)');

                    if (container.innerHTML.trim().length < 50) {
                        const history = this.getHistoryChain(item.rcp_no);
                        container.innerHTML = this.generateDetailHtml(item, history);
                    }
                    detailTr.classList.add('expanded');
                    detailTr.style.display = 'table-row';
                    if (icon) icon.style.transform = 'rotate(180deg)';
                } else {
                    detailTr.style.display = 'none';
                    if (icon) icon.style.transform = 'rotate(0deg)';
                }
            };
        });
    },

    generateDetailHtml: function (item, history) {
        const ratioVal = (item.shares_per_old && item.shares_per_old > 0) ? item.shares_per_old.toFixed(2) : '-';
        const ratioPercent = (item.shares_per_old && item.shares_per_old > 0) ? (item.shares_per_old * 100).toFixed(2) : '-';

        const historyOptions = history.length > 1 ? `
            <div style="margin-top:20px; border-top:1px solid rgba(255,255,255,0.05); padding-top:15px;">
                <div style="display:flex; align-items:center; gap:10px;">
                    <span style="font-size:0.85rem; color:#9ca3af;"><i class="fas fa-history"></i> 공시 이력:</span>
                    <select class="stats-select" style="padding: 4px 8px; font-size: 0.8rem;" onchange="bonusIssueView.jumpToHistory(this.value)">
                        <option value="">이전/정정 공시로 이동...</option>
                        ${history.map(h => `
                            <option value="${h.rcp_no}" ${h.rcp_no === item.rcp_no ? 'selected disabled' : ''}>
                                ${h.disclosure_date || h.date} - ${h.correction_count === 0 ? '최초공시' : h.correction_count + '차정정'} ${h.rcp_no === item.rcp_no ? '(현재)' : ''}
                            </option>
                        `).join('')}
                    </select>
                </div>
            </div>
        ` : '';

        return `
            <div class="stats-detail-container animate-fade-in">
                <div class="stats-detail-grid">
                    <!-- 왼쪽 카드: 증자 개요 -->
                    <div class="stats-card">
                        <h4 style="margin-top:0; color:var(--accent-blue); border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 8px; margin-bottom: 12px;">
                            <i class="fas fa-info-circle"></i> 무상증자 개요
                        </h4>
                        <div style="display: flex; flex-direction: column; gap: 12px; margin-top: 5px;">
                            <div style="display: flex; justify-content: space-between; align-items: baseline;">
                                <span style="color: #9ca3af;">신주배정비율</span>
                                <span style="font-size: 1.25rem; font-weight: 700; color: #4ade80;">1 : ${ratioVal} ${ratioPercent !== '-' ? `(${ratioPercent}%)` : ''}</span>
                            </div>
                            <div style="display: flex; justify-content: space-between; border-bottom: 1px solid rgba(255,255,255,0.03); padding-bottom: 8px;">
                                <span style="color: #9ca3af;">신주발행주식수</span>
                                <span style="font-weight: 700;">${item.new_shares ? item.new_shares.toLocaleString() : '-'} 주</span>
                            </div>
                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">
                                <div style="display: flex; flex-direction: column; gap: 4px;">
                                    <span style="color: #9ca3af; font-size: 0.8rem;">액면가액</span>
                                    <span style="font-weight: 600;">${item.face_value ? item.face_value.toLocaleString() : '-'} 원</span>
                                </div>
                                <div style="display: flex; flex-direction: column; gap: 4px;">
                                    <span style="color: #9ca3af; font-size: 0.8rem;">증자전 주식수</span>
                                    <span style="font-weight: 600;">${item.pre_issued_shares ? item.pre_issued_shares.toLocaleString() : '-'} 주</span>
                                </div>
                            </div>
                            <div style="display: flex; flex-direction: column; gap: 4px; padding-top: 8px; border-top: 1px solid rgba(255,255,255,0.03);">
                                <span style="color: #9ca3af; font-size: 0.85rem;">무상증자 재원</span>
                                <span style="font-weight: 600; color: #60a5fa; line-height: 1.4;">${item.capital_reserve || '정보 없음'}</span>
                            </div>
                        </div>
                    </div>

                    <!-- 오른쪽 카드: 주요 일정 -->
                    <div class="stats-card">
                        <h4 style="margin-top:0; color:var(--accent-blue); border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 8px; margin-bottom: 15px;">
                            <i class="fas fa-calendar-alt"></i> 주요 일정
                        </h4>
                        <div class="stats-timeline">
                            <div class="stats-timeline-item">
                                <div style="color: #9ca3af;">최초공시일 / 이사회결의</div>
                                <div class="stats-timeline-date">${item.initial_disclosure_date || item.board_resolution_date || '-'}</div>
                            </div>
                            <div class="stats-timeline-item active">
                                <div style="color: #9ca3af;">배정기준일</div>
                                <div class="stats-timeline-date">${item.record_date || '-'}</div>
                            </div>
                            <div class="stats-timeline-item">
                                <div style="color: #9ca3af;">상장예정일</div>
                                <div class="stats-timeline-date" style="color: #facc15;">${item.listing_date || '-'}</div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- 하단 정보 및 액션 버튼 -->
                <div class="stats-info-footer">
                    <div style="margin-right: auto; font-size: 0.85rem; color: #9ca3af;">
                        <span id="bi-footer-status">DART 접수번호: <b>${item.rcp_no}</b></span>
                    </div>
                    <div style="display: flex; gap: 10px;">
                        ${item.ticker ? `
                        <a href="/stock/${item.ticker}" onclick="event.preventDefault(); window._jumpToStock('${item.ticker}', '${item.name}')" class="stats-btn-action stats-btn-stock">
                             <i class="fas fa-search-dollar"></i> 종목 분석
                        </a>
                        ` : ''}
                        <a href="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${item.rcp_no}" target="_blank" class="stats-btn-action stats-btn-dart">
                            DART 공시 원문 보기 <i class="fas fa-external-link-alt"></i>
                        </a>
                    </div>
                </div>
                ${historyOptions}
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
    },

    getHistoryChain: function (rcpNo) {
        const chain = [];
        const itemMap = {};
        this.cachedItems.forEach(it => { itemMap[it.rcp_no] = it; });

        let current = itemMap[rcpNo];
        if (!current) return [];

        // 최상위(최초공시) 찾기
        let root = current;
        while (root.parent_rcp_no && itemMap[root.parent_rcp_no]) {
            root = itemMap[root.parent_rcp_no];
        }

        // 최상위부터 하향 탐색하며 체인 생성 (정정 공시들이 여러 개일 수 있으므로)
        const findChildren = (node) => {
            chain.push(node);
            const children = this.cachedItems.filter(it => it.parent_rcp_no === node.rcp_no);
            children.forEach(child => findChildren(child));
        };
        findChildren(root);

        // 중복 제거 및 시간순 정렬
        return [...new Set(chain)].sort((a, b) => {
            const dateA = a.disclosure_date || a.date || "";
            const dateB = b.disclosure_date || b.date || "";
            return dateA.localeCompare(dateB);
        });
    },

    jumpToHistory: function (rcpNo) {
        const target = this.cachedItems.find(it => it.rcp_no === rcpNo);
        if (!target) return;

        const year = (target.disclosure_date || target.date || "").substring(0, 4);
        const yearSelect = document.getElementById('bi-year-select');
        
        if (yearSelect && yearSelect.value !== year) {
            yearSelect.value = year;
            this.renderTable(this.cachedItems, year);
        }

        setTimeout(() => {
            const targetRow = document.querySelector(`.bi-row[data-rcp-no="${rcpNo}"]`);
            if (targetRow) {
                targetRow.scrollIntoView({ behavior: 'smooth', block: 'center' });
                targetRow.style.outline = '2px solid var(--accent-blue)';
                setTimeout(() => targetRow.style.outline = 'none', 2000);
                
                const detailRow = targetRow.nextElementSibling;
                if (detailRow && detailRow.style.display === 'none') {
                    targetRow.click();
                }
            }
        }, 100);
    }
};
