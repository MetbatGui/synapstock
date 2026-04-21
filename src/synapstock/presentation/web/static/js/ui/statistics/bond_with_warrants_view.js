/**
 * @fileoverview 신주인수권부사채(Bond with Warrants) 분석 뷰 모듈.
 * 
 * 구글 드라이브에서 동기화된 BW 발행 결정 공시 데이터를 시각화합니다.
 */

export const bondWithWarrantsView = {
    /**
     * 신주인수권부사채 분석 뷰를 렌더링합니다.
     */
    render: async function (container) {
        this.mainContainer = container;
        container.innerHTML = `
            <div class="stats-container stats-narrow animate-fade-in">
                <div class="stats-header">
                    <h2><i class="fas fa-file-invoice-dollar"></i> 신주인수권부사채(BW) 발행 결정 분석</h2>
                    <div class="stats-filters">
                        <select id="bw-year-select" class="stats-select" title="연도 선택">
                            <option value="2026">2026년</option>
                            <option value="all">전체 연도</option>
                        </select>
                        <button id="sync-bw-btn" class="stats-btn-refresh" title="최신 데이터 동기화">
                            <i class="fas fa-sync-alt"></i>
                        </button>
                    </div>
                </div>
                
                <div class="stats-table-wrapper">
                    <table class="stats-table" id="bw-table">
                        <thead>
                            <tr>
                                <th style="width: 120px;">공시일</th>
                                <th>상호 (종목명)</th>
                                <th style="width: 80px;">회차</th>
                                <th style="width: 100px; text-align:right;">권면총액</th>
                                <th style="width: 100px; text-align:right;">행사가액</th>
                                <th style="width: 120px; text-align:right;">납입일</th>
                                <th style="width: 70px; text-align:center;">상세</th>
                            </tr>
                        </thead>
                        <tbody id="bw-tbody">
                            <tr><td colspan="7" class="stats-loader">데이터를 불러오는 중...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>
        `;

        this.initEventListeners();
        await this.loadData();
    },

    initEventListeners: function () {
        const syncBtn = document.getElementById('sync-bw-btn');
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

        const yearSelect = document.getElementById('bw-year-select');
        if (yearSelect) {
            yearSelect.onchange = () => {
                this.renderTable(this.cachedItems, yearSelect.value);
            };
        }
    },

    cachedItems: [],

    loadData: async function (forceSync = false) {
        try {
            const baseUrl = '/api/statistics/bond-with-warrants';
            const url = forceSync ? `${baseUrl}/sync` : baseUrl;
            const method = forceSync ? 'POST' : 'GET';
            
            const response = await fetch(url, { method });
            const data = await response.json();
            const items = data.items || data || [];

            items.sort((a, b) => b.date.localeCompare(a.date));
            this.cachedItems = this.calculateCorrectionOrders(items);

            this.updateYearOptions(items);
            const yearSelect = document.getElementById('bw-year-select');
            this.renderTable(this.cachedItems, yearSelect ? yearSelect.value : 'all');

        } catch (err) {
            console.error('Failed to load BW data:', err);
            const tbody = document.getElementById('bw-tbody');
            if (tbody) tbody.innerHTML = `<tr><td colspan="7" class="stats-error">로드 실패: ${err.message}</td></tr>`;
        }
    },

    updateYearOptions: function (items) {
        const yearSelect = document.getElementById('bw-year-select');
        if (!yearSelect) return;

        const currentValue = yearSelect.value;
        yearSelect.innerHTML = '<option value="all">전체 연도</option>';

        const years = [...new Set(items.map(item => item.date ? item.date.substring(0, 4) : "")) ]
            .filter(y => y && y.length === 4)
            .sort((a, b) => b.localeCompare(a));

        years.forEach(year => {
            const option = document.createElement('option');
            option.value = year;
            option.textContent = `${year}년`;
            yearSelect.appendChild(option);
        });

        if (years.includes("2026")) yearSelect.value = "2026";
        else if (years.length > 0) yearSelect.value = years[0];
    },

    renderTable: function (items, selectedYear) {
        const tbody = document.getElementById('bw-tbody');
        if (!tbody) return;

        let filteredItems = items;
        if (selectedYear && selectedYear !== "all") {
            filteredItems = items.filter(item => item.date && item.date.startsWith(selectedYear));
        }

        if (filteredItems.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="stats-empty">데이터가 없습니다.</td></tr>';
            return;
        }

        tbody.innerHTML = '';
        filteredItems.forEach(item => {
            const tr = document.createElement('tr');
            tr.className = 'bw-row'; 
            tr.style.cursor = 'pointer';
            tr.innerHTML = `
                <td style="color:#9ca3af;">${item.date}</td>
                <td style="font-weight:600; color:#e5e7eb;">
                    ${item.ticker ? `<a href="/stock/${item.ticker}" onclick="event.stopPropagation(); event.preventDefault(); window._jumpToStock('${item.ticker}', '${item.name}')" style="color:inherit; text-decoration:none;">${item.name}</a>` : item.name}
                    ${item.is_correction ? `<span style="font-size:0.75rem; background:#ef4444; color:white; padding:1px 4px; border-radius:3px; margin-left:5px;">기재정정 ${item.correction_count > 0 ? `+${item.correction_count}` : ''}</span>` : ''}
                </td>
                <td style="text-align:center; color:#60a5fa;">${item.bond_round}</td>
                <td style="text-align:right; font-weight:600; color:#facc15;">${this.formatUnit(item.bond_amount)}</td>
                <td style="text-align:right; color:#4ade80;">${item.exercise_price ? item.exercise_price.toLocaleString() : '-'}</td>
                <td style="text-align:right; color:#9ca3af;">${item.payment_date || '-'}</td>
                <td style="text-align:center;"><span class="expand-icon">▼</span></td>
            `;
            tr.dataset.rcpNo = item.rcp_no;

            const detailTr = document.createElement('tr');
            detailTr.className = 'detail-row';
            detailTr.style.display = 'none';
            detailTr.innerHTML = `<td colspan="7" class="detail-container"></td>`;

            tbody.appendChild(tr);
            tbody.appendChild(detailTr);

            tr.onclick = () => {
                const container = detailTr.querySelector('.detail-container');
                const icon = tr.querySelector('.expand-icon');
                const isHidden = detailTr.style.display === 'none';

                if (isHidden) {
                    // 다른 열려있는 상세 행 닫기
                    const tbody = tr.parentElement;
                    tbody.querySelectorAll('.detail-row').forEach(row => {
                        row.style.display = 'none';
                        row.classList.remove('expanded');
                    });
                    tbody.querySelectorAll('.expand-icon').forEach(ic => ic.style.transform = 'rotate(0deg)');

                    if (container.innerHTML.trim().length < 50) {
                        const history = this.getHistoryChain(item.rcp_no);
                        container.innerHTML = this.generateDetailHtml(item, history);
                    }
                    detailTr.style.display = 'table-row';
                    detailTr.classList.add('expanded');
                    if (icon) icon.style.transform = 'rotate(180deg)';
                } else {
                    detailTr.style.display = 'none';
                    detailTr.classList.remove('expanded');
                    if (icon) icon.style.transform = 'rotate(0deg)';
                }
            };
        });
    },

    generateDetailHtml: function (item, history = []) {
        const total = item.total_fund || item.bond_amount;
        const segments = [
            { label: '시설', amount: item.fund_facility, class: 'segment-facility' },
            { label: '운영', amount: item.fund_operation, class: 'segment-operation' },
            { label: '영업양수', amount: item.fund_acquisition_biz, class: 'segment-acquisition-biz' },
            { label: '타법인', amount: item.fund_acquisition_sec, class: 'segment-acquisition' },
            { label: '채무상환', amount: item.fund_debt_repayment, class: 'segment-debt' },
            { label: '기타', amount: item.fund_etc, class: 'segment-etc' }
        ].filter(s => s.amount > 0);

        const stackedBarHtml = segments.map(s => {
            const pct = ((s.amount / total) * 100).toFixed(1);
            return `<div class="fund-segment ${s.class}" style="width: ${pct}%" title="${s.label}: ${this.formatUnit(s.amount)} (${pct}%)"></div>`;
        }).join('');

        return `
            <div class="stats-detail-container animate-fade-in">
                <div class="stats-detail-grid" style="grid-template-columns: 1fr 1fr 1.2fr;">
                    <!-- 카드 1: 자금조달 목적 -->
                    <div class="stats-card">
                        <h4 class="card-title"><i class="fas fa-coins"></i> 자금조달 목적 및 규모</h4>
                        <div class="fund-summary">
                            <span class="label">총 발행 금액</span>
                            <span class="value headline">${this.formatUnit(item.bond_amount)}</span>
                        </div>
                        <div class="fund-stacked-container">
                            <div class="fund-stacked-bar">${stackedBarHtml}</div>
                            <div class="fund-legend">
                                ${segments.map(s => `
                                    <div class="fund-legend-item">
                                        <div class="legend-dot ${s.class}"></div>
                                        <span class="fund-label-row">
                                            <span class="fund-amount-text">${s.label}: <b>${this.formatUnit(s.amount)}</b></span>
                                            <span class="fund-pct-text">(${( (s.amount / total) * 100).toFixed(1)}%)</span>
                                        </span>
                                    </div>
                                `).join('')}
                            </div>
                        </div>
                    </div>

                    <!-- 카드 2: 상세 발행 조건 -->
                    <div class="stats-card">
                        <h4 class="card-title"><i class="fas fa-file-signature"></i> 상세 발행 조건</h4>
                        <div class="info-list">
                            <div class="info-item">
                                <span class="label">회차 / 종류</span>
                                <span class="value">${item.bond_round} / ${item.bond_type}</span>
                            </div>
                            <div class="info-item">
                                <span class="label">발행방법</span>
                                <span class="value highlight">${item.issue_method}</span>
                            </div>
                            <div class="info-item">
                                <span class="label">행사가액</span>
                                <span class="value highlight">${item.exercise_price ? item.exercise_price.toLocaleString() + ' 원' : '-'}</span>
                            </div>
                            <div class="info-item">
                                <span class="label">신주인수권 비율</span>
                                <span class="value">${item.warrant_ratio}%</span>
                            </div>
                            <div class="info-item">
                                <span class="label">발행주식수</span>
                                <span class="value">${item.new_shares ? item.new_shares.toLocaleString() + ' 주' : '-'}</span>
                            </div>
                            <div class="info-item">
                                <span class="label">주식대비비율</span>
                                <span class="value" style="color:#4ade80;">${item.shares_ratio}%</span>
                            </div>
                        </div>
                    </div>

                    <!-- 카드 3: 주요 일정 -->
                    <div class="stats-card">
                        <h4 class="card-title"><i class="fas fa-calendar-check"></i> 주요 일정</h4>
                        <div class="stats-timeline">
                            <div class="stats-timeline-item">
                                <div class="label">청약 / 납입일</div>
                                <div class="stats-timeline-date">${item.subscription_date ? item.subscription_date + ' / ' : ''}${item.payment_date || '-'}</div>
                            </div>
                            <div class="stats-timeline-item active">
                                <div class="label">권리행사기간</div>
                                <div class="stats-timeline-date" style="font-size:0.85rem;">
                                    ${item.exercise_start_date || '-'} ~<br/>${item.exercise_end_date || '-'}
                                </div>
                            </div>
                            <div class="stats-timeline-item">
                                <div class="label">사채만기일</div>
                                <div class="stats-timeline-date headline" style="color:#facc15;">${item.maturity_date || '-'}</div>
                            </div>
                        </div>
                        <div class="info-footer">
                            <i class="fas fa-info-circle"></i> 최초 공시: ${item.initial_disclosure_date || '-'} <br/>
                            <i class="fas fa-gavel"></i> 이사회결의: ${item.board_resolution_date || '-'}
                        </div>
                    </div>
                </div>

                <div class="stats-info-footer">
                    <div class="footer-left">
                         <i class="fas fa-fingerprint"></i> 접수번호: ${item.rcp_no}
                         ${item.parent_rcp_no ? `<br/><i class="fas fa-link"></i> 상위공시: <a href="#" onclick="bondWithWarrantsView.jumpToHistory('${item.parent_rcp_no}'); return false;" style="color:var(--accent-blue); text-decoration:underline;">${item.parent_rcp_no}</a>` : ''}
                    </div>
                    <div class="footer-actions">
                        ${item.ticker ? `
                        <a href="/stock/${item.ticker}" onclick="event.preventDefault(); window._jumpToStock('${item.ticker}', '${item.name}')" class="stats-btn-action stats-btn-stock">
                             <i class="fas fa-search-dollar"></i> 종목 분석
                        </a>
                        ` : ''}
                        <a href="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${item.rcp_no}" target="_blank" class="stats-btn-action stats-btn-dart">
                            DART 원문 <i class="fas fa-external-link-alt"></i>
                        </a>
                    </div>
                </div>

                ${history.length > 1 ? `
                <div style="margin-top:20px; border-top:1px solid rgba(255,255,255,0.05); padding-top:15px;">
                    <div style="display:flex; align-items:center; gap:10px;">
                        <span style="font-size:0.85rem; color:#9ca3af;"><i class="fas fa-history"></i> 공시 이력:</span>
                        <select class="stats-select" style="padding: 4px 8px; font-size: 0.8rem;" onchange="bondWithWarrantsView.jumpToHistory(this.value)">
                            <option value="">이전/정정 공시로 이동...</option>
                            ${history.map(h => `
                                <option value="${h.rcp_no}" ${h.rcp_no === item.rcp_no ? 'selected disabled' : ''}>
                                    ${h.date} - ${h.correction_count === 0 ? '최초공시' : h.correction_count + '차정정'} ${h.rcp_no === item.rcp_no ? '(현재)' : ''}
                                </option>
                            `).join('')}
                        </select>
                    </div>
                </div>
                ` : ''}
            </div>
        `;
    },

    jumpToHistory: function (rcpNo) {
        // 1. 현재 필터에서 이미 보이는 행인지 확인
        let targetRow = document.querySelector(`.bw-row[data-rcp-no="${rcpNo}"]`);
        
        // 2. 안 보인다면 필터 변경 및 재렌더링
        if (!targetRow) {
            const year = (target.date || "").substring(0, 4);
            const yearSelect = document.getElementById('bw-year-select');
            if (yearSelect && yearSelect.value !== year) {
                yearSelect.value = year;
                this.renderTable(this.cachedItems, year);
            }
        }

        // 3. 렌더링 완료를 기다린 후 이동 및 상세 열기
        setTimeout(() => {
            targetRow = document.querySelector(`.bw-row[data-rcp-no="${rcpNo}"]`);
            if (targetRow) {
                targetRow.scrollIntoView({ behavior: 'smooth', block: 'center' });
                targetRow.style.outline = '2px solid var(--accent-blue)';
                targetRow.style.boxShadow = '0 0 15px rgba(96, 165, 250, 0.5)';
                setTimeout(() => {
                    targetRow.style.outline = 'none';
                    targetRow.style.boxShadow = 'none';
                }, 2000);
                
                const detailRow = targetRow.nextElementSibling;
                if (detailRow && detailRow.style.display === 'none') {
                    // 강제 오픈
                    targetRow.click();
                }
            }
        }, 200);
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

        let root = current;
        while (root.parent_rcp_no && itemMap[root.parent_rcp_no]) {
            root = itemMap[root.parent_rcp_no];
        }

        const findChildren = (node) => {
            chain.push(node);
            const children = this.cachedItems.filter(it => it.parent_rcp_no === node.rcp_no);
            children.forEach(child => findChildren(child));
        };
        findChildren(root);

        return [...new Set(chain)].sort((a, b) => {
            return (a.date || "").localeCompare(b.date || "");
        });
    },

    formatUnit: function (value) {
        if (!value || value === 0) return '0';
        if (value >= 100000000) return `${(value / 100000000).toFixed(1)}억`;
        if (value >= 10000) return `${(value / 10000).toFixed(0)}만`;
        return value.toLocaleString();
    }
};
