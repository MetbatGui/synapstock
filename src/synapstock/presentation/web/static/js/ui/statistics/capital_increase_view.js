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
            <div class="stats-container stats-narrow animate-fade-in">
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
                                <th style="width: 200px;">증자방식</th>
                                <th style="width: 100px; text-align:right;">조달금액</th>
                                <th style="width: 120px; text-align:right;">배정비율</th>
                                <th style="width: 130px; text-align:right;">납입일</th>
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

            this.cachedItems = this.calculateCorrectionOrders(items);

            // 연도 드롭다운 업데이트
            this.updateYearOptions(items);

            // 테이블 렌더링 (기본값: 전체 또는 현재 선택된 연도)
            const yearSelect = document.getElementById('ci-year-select');
            this.renderTable(this.cachedItems, yearSelect ? yearSelect.value : 'all');

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
            
            const ratioVal = (item.shares_per_old && item.shares_per_old > 0) ? item.shares_per_old.toFixed(2) : '-';
            const ratioPercent = (item.shares_per_old && item.shares_per_old > 0) ? (item.shares_per_old * 100).toFixed(2) : '-';

            // 메인 행 (Basic Info)
            const tr = document.createElement('tr');
            tr.className = 'ci-row';
            tr.dataset.rcpNo = item.rcp_no; // 식별자 추가
            tr.style.cursor = 'pointer';
            tr.innerHTML = `
                <td style="color:#9ca3af;">${item.disclosure_date || item.date}</td>
                <td style="font-weight:600; color:#e5e7eb;">
                    ${item.name}
                    ${item.is_correction ? `<span style="font-size:0.75rem; background:#ef4444; color:white; padding:1px 4px; border-radius:3px; margin-left:5px;">기재정정 ${item.correction_count > 0 ? `+${item.correction_count}` : ''}</span>` : ''}
                </td>
                <td style="color:#60a5fa;">${item.method}</td>
                <td style="text-align:right; font-weight:600; color:#facc15;">${this.formatUnit(total)}</td>
                <td style="text-align:right; color:#4ade80; font-weight:600;">1 : ${ratioVal} ${ratioPercent !== '-' ? `(${ratioPercent}%)` : ''}</td>
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
                    // 다른 열려있는 상세 행 닫기
                    tbody.querySelectorAll('.detail-row').forEach(row => {
                        row.style.display = 'none';
                        row.classList.remove('expanded');
                    });
                    tbody.querySelectorAll('.expand-icon').forEach(ic => ic.style.transform = 'rotate(0deg)');
                    
                    // 데이터 생성 및 표시
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

    /**
     * 상세 보기를 위한 HTML 조각을 생성합니다.
     */
    generateDetailHtml: function (item, history) {
        // 자금조달 세부 내역 계산
        const total = (item.fund_facility || 0) + (item.fund_operation || 0) + (item.fund_acquisition || 0) + (item.fund_etc || 0);
        const segments = [
            { label: '시설자금', amount: item.fund_facility, class: 'segment-facility' },
            { label: '운영자금', amount: item.fund_operation, class: 'segment-operation' },
            { label: '타법인 취득', amount: item.fund_acquisition, class: 'segment-acquisition' },
            { label: '기타자금', amount: item.fund_etc, class: 'segment-etc' }
        ].filter(s => s.amount > 0);

        const stackedBarHtml = segments.map(s => {
            const pct = ((s.amount / total) * 100).toFixed(1);
            return `<div class="fund-segment ${s.class}" style="width: ${pct}%" title="${s.label}: ${this.formatUnit(s.amount)} (${pct}%)"></div>`;
        }).join('');

        const legendHtml = segments.map(s => `
            <div class="fund-legend-item">
                <div class="legend-dot ${s.class}"></div>
                <span class="fund-label-row">
                    <span class="fund-amount-text">${s.label}: <b>${this.formatUnit(s.amount)}</b></span>
                    <span class="fund-pct-text">(${( (s.amount / total) * 100).toFixed(1)}%)</span>
                </span>
            </div>
        `).join('');

        const ratioVal = (item.shares_per_old && item.shares_per_old > 0) ? item.shares_per_old.toFixed(2) : '-';
        const ratioPercent = (item.shares_per_old && item.shares_per_old > 0) ? (item.shares_per_old * 100).toFixed(2) : '-';

        const historyOptions = history.length > 1 ? `
            <div style="margin-top:20px; border-top:1px solid rgba(255,255,255,0.05); padding-top:15px;">
                <div style="display:flex; align-items:center; gap:10px;">
                    <span style="font-size:0.85rem; color:#9ca3af;"><i class="fas fa-history"></i> 공시 이력:</span>
                    <select class="stats-select" style="padding: 4px 8px; font-size: 0.8rem;" onchange="capitalIncreaseView.jumpToHistory(this.value)">
                        <option value="">이이전/정정 공시로 이동...</option>
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
                <div class="stats-detail-grid" style="grid-template-columns: 1fr 1fr 1.2fr;">
                    <!-- 카드 1: 자금조달 목적 및 현황 -->
                    <div class="stats-card">
                        <h4 style="margin-top:0; color:var(--accent-blue); border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 8px; margin-bottom: 15px;">
                            <i class="fas fa-coins"></i> 자금조달 목적 및 규모
                        </h4>
                        <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 5px;">
                            <span style="color: #9ca3af; font-size: 0.9rem;">총 조달 금액</span>
                            <span style="font-size: 1.4rem; font-weight: 700; color: #facc15;">${this.formatUnit(total)}</span>
                        </div>
                        
                        <div class="fund-stacked-container">
                            <div class="fund-stacked-bar">
                                ${stackedBarHtml}
                            </div>
                            <div class="fund-legend">
                                ${legendHtml}
                            </div>
                        </div>
                    </div>

                    <!-- 카드 2: 상세 발행 정보 -->
                    <div class="stats-card">
                        <h4 style="margin-top:0; color:var(--accent-blue); border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 8px; margin-bottom: 15px;">
                            <i class="fas fa-file-invoice-dollar"></i> 상세 발행 정보
                        </h4>
                        <div style="display: flex; flex-direction: column; gap: 12px;">
                            <div style="display: flex; justify-content: space-between; border-bottom: 1px solid rgba(255,255,255,0.03); padding-bottom: 8px;">
                                <span style="color: #9ca3af;">증자방식</span>
                                <span style="font-weight: 600; color: #60a5fa;">${item.method || '-'}</span>
                            </div>
                            <div style="display: flex; justify-content: space-between; border-bottom: 1px solid rgba(255,255,255,0.03); padding-bottom: 8px;">
                                <span style="color: #9ca3af;">발행가액</span>
                                <span style="font-weight: 600;">${item.issue_price ? item.issue_price.toLocaleString() : '-'} 원</span>
                            </div>
                            <div style="display: flex; justify-content: space-between; border-bottom: 1px solid rgba(255,255,255,0.03); padding-bottom: 8px;">
                                <span style="color: #9ca3af;">신주배정비율</span>
                                <span style="font-weight: 600; color: #4ade80;">1 : ${ratioVal} ${ratioPercent !== '-' ? `(${ratioPercent}%)` : ''}</span>
                            </div>
                            <div style="display: flex; justify-content: space-between; border-bottom: 1px solid rgba(255,255,255,0.03); padding-bottom: 8px;">
                                <span style="color: #9ca3af;">신주발행주식수</span>
                                <span style="font-weight: 600;">${item.new_shares ? item.new_shares.toLocaleString() : '-'} 주</span>
                            </div>
                            <div style="display: flex; justify-content: space-between;">
                                <span style="color: #9ca3af;">액면가 / 전주식수</span>
                                <span style="font-weight: 600; color: #9ca3af;">${item.face_value || '-'} / ${item.pre_issued_shares ? item.pre_issued_shares.toLocaleString() : '-'}</span>
                            </div>
                        </div>
                    </div>

                    <!-- 카드 3: 주요 일정 -->
                    <div class="stats-card">
                        <h4 style="margin-top:0; color:var(--accent-blue); border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 8px; margin-bottom: 15px;">
                            <i class="fas fa-calendar-alt"></i> 주요 일정
                        </h4>
                        <div class="stats-timeline">
                            <div class="stats-timeline-item">
                                <div style="color: #9ca3af;">배정기준일</div>
                                <div class="stats-timeline-date">${item.record_date || '-'}</div>
                            </div>
                            <div class="stats-timeline-item active">
                                <div style="color: #9ca3af;">청약 / 납입일</div>
                                <div class="stats-timeline-date" style="color: #fff;">${item.subscription_date ? item.subscription_date + ' / ' : ''}${item.payment_date || '-'}</div>
                            </div>
                            <div class="stats-timeline-item">
                                <div style="color: #9ca3af;">상장예정일</div>
                                <div class="stats-timeline-date" style="color: #facc15;">${item.listing_date || '-'}</div>
                            </div>
                        </div>
                        <div style="margin-top: 20px; font-size: 0.8rem; color: #64748b; font-style: italic;">
                            <i class="fas fa-info-circle"></i> 최초 공시: ${item.initial_disclosure_date || '-'} / 이사회결의: ${item.board_resolution_date || '-'}
                        </div>
                    </div>
                </div>

                <!-- 하단 정보 및 액션 버튼 -->
                <div class="stats-info-footer">
                    <div style="margin-right: auto; font-size: 0.85rem; color: #9ca3af;">
                         <i class="fas fa-chart-pie" style="margin-right: 5px;"></i> 증자후 예상 발행주식총수: <b style="color: #e5e7eb;">${(item.pre_issued_shares + (item.new_shares || 0)).toLocaleString()}</b> 주<br/>
                         <i class="fas fa-fingerprint"></i> 접수번호: ${item.rcp_no}
                         ${item.parent_rcp_no ? `<br/><i class="fas fa-link"></i> 상위공시: <a href="#" onclick="capitalIncreaseView.jumpToHistory('${item.parent_rcp_no}'); return false;" style="color:var(--accent-blue); text-decoration:underline;">${item.parent_rcp_no}</a>` : ''}
                    </div>
                    <div style="display: flex; gap: 10px;">
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
                ${historyOptions}
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
    },

    /**
     * 모든 공시 항목의 기재정정 차수를 계산합니다.
     * @param {Array} items - 유상증자 공시 항목 리스트
     * @returns {Array} 차수 정보가 추가된 항목 리스트
     */
    calculateCorrectionOrders: function (items) {
        if (!items || items.length === 0) return [];

        // 1. 빠른 조회를 위한 맵 생성 (rcp_no -> item)
        const itemMap = {};
        items.forEach(item => {
            if (item.rcp_no) itemMap[item.rcp_no] = item;
        });

        // 2. 각 항목의 차수 계산
        return items.map(item => {
            let count = 0;
            let current = item;

            // 상위 공시(parent_rcp_no)가 있고, 그 공시가 실제 데이터에 존재하는 동안 추적
            while (current && current.parent_rcp_no && itemMap[current.parent_rcp_no]) {
                count++;
                current = itemMap[current.parent_rcp_no];
                
                // 무한 루프 방지 (자기 참조 방지)
                if (current.rcp_no === item.rcp_no) break;
            }

            return { ...item, correction_count: count };
        });
    },

    /**
     * 특정 공시와 연관된 모든 전후 공시 이력을 찾아 계보를 만듭니다.
     * @param {string} rcpNo - 기준 공시 번호
     * @returns {Array} 시간 순서대로 정렬된 히스토리 아이템 배열
     */
    getHistoryChain: function (rcpNo) {
        const currentItem = this.cachedItems.find(it => it.rcp_no === rcpNo);
        if (!currentItem) return [];

        // 1. 모든 아이템을 rcp_no 맵과 종목별 그룹으로 분리
        const allItemsOfStock = this.cachedItems.filter(it => it.name === currentItem.name);
        
        // 2. 부모/자식 포인터를 따라가지 않고, 같은 종목 내에서 연관된 이력을 모두 수집
        // (실제 데이터상 rcp_no 체인이 연결되어 있지 않더라도 같은 종목의 유상증자 이력을 보여주는 것이 유용함)
        // 여기서는 엄격한 '정정' 관계만 보여주기 위해 parent_rcp_no를 추적하여 루트를 찾고 다시 내려오는 방식 권장
        
        let root = currentItem;
        const itemMap = {};
        this.cachedItems.forEach(it => { if(it.rcp_no) itemMap[it.rcp_no] = it; });

        // 루트(최초공시) 찾기
        while (root && root.parent_rcp_no && itemMap[root.parent_rcp_no]) {
            root = itemMap[root.parent_rcp_no];
        }

        // 해당 루트로부터 파생된 모든 가지 수집 (정렬된 일일 수급 리스트이므로 날짜순 탐색이 유리)
        const chain = allItemsOfStock.filter(it => {
            let temp = it;
            while(temp && temp.parent_rcp_no) {
                if(temp.rcp_no === root.rcp_no || temp.parent_rcp_no === root.rcp_no) return true;
                temp = itemMap[temp.parent_rcp_no];
            }
            return it.rcp_no === root.rcp_no;
        });

        return chain.sort((a, b) => {
            const da = a.disclosure_date || a.date || "";
            const db = b.disclosure_date || b.date || "";
            return da.localeCompare(db);
        });
    },

    /**
     * 특정 공시 번호로 화면을 이동하고 상세 내용을 펼칩니다.
     * @param {string} rcpNo - 이동할 타겟 공시 번호
     */
    jumpToHistory: async function (rcpNo) {
        const target = this.cachedItems.find(it => it.rcp_no === rcpNo);
        if (!target) return;

        const year = (target.disclosure_date || target.date || "").substring(0, 4);
        const yearSelect = document.getElementById('ci-year-select');
        
        // 1. 연도 필터 변경 및 재렌더링
        if (yearSelect && yearSelect.value !== year) {
            yearSelect.value = year;
            this.renderTable(this.cachedItems, year);
        }

        // 2. DOM에서 해당 행 찾기 (렌더링 직후이므로 약간의 지연 필요할 수 있음)
        setTimeout(() => {
            const targetRow = document.querySelector(`.ci-row[data-rcp-no="${rcpNo}"]`);
            if (targetRow) {
                // 부드럽게 스크롤
                targetRow.scrollIntoView({ behavior: 'smooth', block: 'center' });
                
                // 강조 표시
                targetRow.style.outline = '2px solid var(--accent-blue)';
                setTimeout(() => targetRow.style.outline = 'none', 2000);
                
                const detailRow = targetRow.nextElementSibling;
                if (detailRow && detailRow.style.display === 'none') {
                    // 강제 오픈
                    targetRow.click();
                } else if (detailRow && detailRow.classList.contains('expanded')) {
                    // 이미 열려있다면 유지
                }
            }
        }, 150);
    }
};

