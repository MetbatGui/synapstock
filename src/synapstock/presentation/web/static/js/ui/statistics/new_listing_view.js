/**
 * @fileoverview 신규 상장주(IPO) 분석 뷰 모듈.
 * 
 * 구글 드라이브에서 동기화된 IPO 데이터를 바탕으로 경쟁률, 확약 비율, 
 * 상장일 수익률 등을 대시보드 형태로 시각화합니다.
 */

export const newListingView = {
    /**
     * 신규 상장 분석 뷰를 렌더링합니다.
     * @param {HTMLElement} container - 렌더링될 대상 컨테이너.
     */
    render: async function (container) {
        this.mainContainer = container;
        container.innerHTML = `
            <div class="stats-container animate-fade-in">
                <div class="stats-header">
                    <h2><i class="fas fa-gem"></i> 신규 상장주(IPO) 분석 대시보드</h2>
                    <div class="stats-filters">
                        <select id="ipo-year-select" class="stats-select" title="연도 선택">
                            <option value="2026">2026년</option>
                            <option value="all">전체</option>
                        </select>
                        <button id="sync-new-listing-btn" class="stats-btn-refresh" title="최신 데이터 동기화">
                            <i class="fas fa-sync-alt"></i>
                        </button>
                    </div>
                </div>
                
                <div id="ipo-summary-cards" class="stats-card-group">
                    <!-- 요약 카드가 동적으로 삽입됩니다 -->
                </div>

                <div class="stats-table-wrapper">
                    <table class="stats-table">
                        <thead>
                            <tr>
                                <th style="width: 100px;">상장일</th>
                                <th>종목명 (시장/업종)</th>
                                <th style="width: 100px; text-align:right;">공모가</th>
                                <th style="width: 200px;" class="col-competition">기관 경쟁률</th>
                                <th style="width: 140px; text-align:right;">수익률(종가)</th>
                                <th style="width: 60px; text-align:center;">상세</th>
                            </tr>
                        </thead>
                        <tbody id="new-listing-tbody">
                            <tr><td colspan="6" class="stats-loader">데이터를 분석 중...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>
        `;

        this.initEventListeners();
        await this.loadData();
    },

    /**
     * 필터 및 버튼 이벤트를 초기화합니다.
     */
    initEventListeners: function () {
        const syncBtn = document.getElementById('sync-new-listing-btn');
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

        const yearSelect = document.getElementById('ipo-year-select');
        if (yearSelect) {
            yearSelect.onchange = () => {
                this.renderTable(this.cachedItems, yearSelect.value);
            };
        }
    },

    cachedItems: [],

    /**
     * 백엔드 API로부터 IPO 데이터를 로드합니다.
     */
    loadData: async function (forceSync = false) {
        try {
            const response = await fetch(`/api/statistics/new-listing?force_sync=${forceSync}`);
            const data = await response.json();
            const items = data.items || [];

            // 상장일 기준 내림차순 정렬
            items.sort((a, b) => (b.listing_date || "").localeCompare(a.listing_date || ""));

            this.cachedItems = items;
            this.updateYearOptions(items);
            
            const yearSelect = document.getElementById('ipo-year-select');
            this.renderTable(items, yearSelect ? yearSelect.value : 'all');
            this.renderSummary(items);

        } catch (err) {
            console.error('Failed to load IPO data:', err);
            const tbody = document.getElementById('new-listing-tbody');
            if (tbody) tbody.innerHTML = `<tr><td colspan="6" class="stats-error">로드 실패: ${err.message}</td></tr>`;
        }
    },

    /**
     * 연도 필터 옵션을 동적으로 업데이트합니다.
     */
    updateYearOptions: function (items) {
        const yearSelect = document.getElementById('ipo-year-select');
        if (!yearSelect) return;

        const currentVal = yearSelect.value;
        const years = [...new Set(items.map(it => (it.listing_date || "").substring(0, 4)))]
            .filter(y => y && y.length === 4)
            .sort((a, b) => b.localeCompare(a));

        yearSelect.innerHTML = '<option value="all">전체</option>';
        years.forEach(y => {
            const opt = document.createElement('option');
            opt.value = y;
            opt.textContent = `${y}년`;
            yearSelect.appendChild(opt);
        });

        if (years.includes(currentVal)) yearSelect.value = currentVal;
        else if (years.length > 0 && currentVal === '2026') yearSelect.value = years.includes('2026') ? '2026' : years[0];
    },

    /**
     * 상단 요약 카드를 렌더링합니다.
     */
    renderSummary: function (items) {
        const container = document.getElementById('ipo-summary-cards');
        if (!container) return;

        const yearSelect = document.getElementById('ipo-year-select');
        const selectedYear = yearSelect ? yearSelect.value : 'all';
        const filtered = selectedYear === 'all' ? items : items.filter(it => it.listing_date.startsWith(selectedYear));

        if (filtered.length === 0) {
            container.innerHTML = '';
            return;
        }

        const avgComp = filtered.reduce((acc, it) => acc + (it.institutional_competition || 0), 0) / filtered.length;
        const avgReturn = filtered.reduce((acc, it) => acc + (it.listing_day_change_pct || 0), 0) / filtered.length;
        const totalIPOs = filtered.length;

        container.innerHTML = `
            <div class="card stats-summary-box animate-slide-up" style="animation-delay: 0.1s">
                <span class="label">총 상장 건수</span>
                <span class="value">${totalIPOs} <small>건</small></span>
            </div>
            <div class="card stats-summary-box animate-slide-up" style="animation-delay: 0.2s">
                <span class="label">평균 기관 경쟁률</span>
                <span class="value" style="color: #f97316;">${avgComp.toFixed(1)} <small>: 1</small></span>
            </div>
            <div class="card stats-summary-box animate-slide-up" style="animation-delay: 0.3s">
                <span class="label">평균 종가 수익률</span>
                <span class="value" style="color: #ef4444;">${avgReturn >= 0 ? '+' : ''}${avgReturn.toFixed(1)} <small>%</small></span>
            </div>
        `;
    },

    /**
     * IPO 데이터 테이블을 렌더링합니다.
     */
    renderTable: function (items, selectedYear) {
        const tbody = document.getElementById('new-listing-tbody');
        if (!tbody) return;

        const filtered = selectedYear === 'all' ? items : items.filter(it => it.listing_date.startsWith(selectedYear));

        if (filtered.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="stats-empty">상장 데이터가 없습니다.</td></tr>';
            return;
        }

        tbody.innerHTML = '';
        filtered.forEach((it, idx) => {
            const tr = document.createElement('tr');
            tr.className = 'row-ipo';
            tr.style.cursor = 'pointer';

            // 경쟁률 스타일
            const comp = it.institutional_competition || 0;
            const compPct = Math.min((comp / 2500) * 100, 100); 
            let compClass = 'comp-cool';
            if (comp >= 1500) compClass = 'comp-hot';
            else if (comp >= 800) compClass = 'comp-warm';

            const ret = it.listing_day_change_pct || 0;
            const noteHtml = it.note ? `<i class="fas fa-info-circle ipo-note-icon" title="${it.note}"></i>` : '';

            // 상태 뱃지 생성
            let statusBadgeHtml = '';
            if (it.status === 'ASSIGNED') {
                const displayBoardName = (it.current_board || '').replace('theme_', '').replace('virtual_', '');
                statusBadgeHtml = `<span class="ipo-status-badge assigned" title="배치 완료: ${displayBoardName}">배치 완료</span>`;
            } else if (it.status === 'IGNORED') {
                statusBadgeHtml = `<span class="ipo-status-badge ignored">제외됨</span>`;
            } else {
                statusBadgeHtml = `<span class="ipo-status-badge pending">대기 중</span>`;
            }

            tr.innerHTML = `
                <td style="color:#9ca3af;">${it.listing_date}</td>
                <td>
                    <div style="display:flex; flex-direction:column;">
                        <div style="display:flex; align-items:center;">
                            ${it.market ? `<span class="ipo-market-badge">${it.market}</span>` : ''}
                            ${statusBadgeHtml}
                            <span style="font-weight:700; color:#f3f4f6;">${it.name}</span>
                            ${noteHtml}
                        </div>
                        <div class="ipo-meta-info" style="font-size:0.75rem; color:#64748b; margin-top:2px;">
                            ${it.sector || ''}
                        </div>
                    </div>
                </td>
                <td style="text-align:right; font-weight:600; color:#e2e8f0;">${(it.offer_price || 0).toLocaleString()}</td>
                <td class="col-competition">
                    <div style="display:flex; align-items:center; gap:8px;">
                        <span class="comp-value">${comp.toLocaleString()} : 1</span>
                        <div class="competition-bar-container" style="flex:1; margin-top:0;">
                            <div class="competition-bar ${compClass}" style="width: ${compPct}%"></div>
                        </div>
                    </div>
                </td>
                <td style="text-align:right;">
                    <span style="font-weight:800; font-size:1.1rem; color:${ret >= 0 ? '#f87171' : '#60a5fa'};">
                        ${ret >= 0 ? '+' : ''}${ret.toFixed(1)}%
                    </span>
                </td>
                <td style="text-align:center;">
                    <span class="expand-icon">▼</span>
                </td>
            `;

            const detailTr = document.createElement('tr');
            detailTr.className = 'detail-row';
            detailTr.style.display = 'none';
            detailTr.innerHTML = `<td colspan="6" class="detail-container"></td>`;

            tbody.appendChild(tr);
            tbody.appendChild(detailTr);

            // 클릭 이벤트 (상세 보기 토글)
            tr.onclick = () => {
                const isExpanded = detailTr.classList.contains('expanded');
                
                // 다른 열린 행 닫기
                tbody.querySelectorAll('.detail-row').forEach(r => {
                    r.classList.remove('expanded');
                    r.style.display = 'none';
                });
                tbody.querySelectorAll('.row-ipo').forEach(r => r.classList.remove('active'));

                if (!isExpanded) {
                    const container = detailTr.querySelector('.detail-container');
                    if (!container.innerHTML) {
                        container.innerHTML = this.generateDetailHtml(it);
                        this.bindDetailRowEvents(container, it); // 동적 버튼 이벤트 바인딩
                    }
                    detailTr.classList.add('expanded');
                    tr.classList.add('active');
                }
            };
        });

        this.bindEventsAfterRender(tbody);
    },

    /**
     * 상세 정보 HTML 생성
     */
    generateDetailHtml: function (it) {
        const openRet = it.offer_price > 0 ? ((it.listing_day_open - it.offer_price) / it.offer_price * 100) : 0;
        const highRet = it.offer_price > 0 ? ((it.listing_day_high - it.offer_price) / it.offer_price * 100) : 0;

        let actionButtons = '';
        if (it.status === 'ASSIGNED') {
            const displayBoardName = (it.current_board || '').replace('theme_', '').replace('virtual_', '');
            actionButtons = `
                <span style="font-size:0.8rem; color:#34d399; font-weight:600; margin-right:8px;"><i class="fas fa-check-circle"></i> 배치됨: ${displayBoardName}</span>
                <button class="stats-btn-action btn-assign btn-jump" data-board="${it.current_board}" style="background:#10b981; border:none; color:white; cursor:pointer;"><i class="fas fa-external-link-alt"></i> 보드로 가기</button>
            `;
        } else if (it.status === 'IGNORED') {
            actionButtons = `
                <span style="font-size:0.8rem; color:#64748b; margin-right:8px;"><i class="fas fa-ban"></i> 제외된 종목</span>
            `;
        } else {
            actionButtons = `
                <button class="stats-btn-action btn-assign" data-ticker="${it.ticker}" data-name="${it.name}" style="background:#3b82f6; border:none; color:white; cursor:pointer;"><i class="fas fa-th-large"></i> 보드에 배치</button>
                <button class="stats-btn-action btn-ignore" data-ticker="${it.ticker}" style="background:#475569; border:none; color:white; cursor:pointer;"><i class="fas fa-eye-slash"></i> 제외</button>
            `;
        }

        return `
            <div class="ipo-detail-grid animate-fade-in">
                <!-- 카드 1: 재무 요약 -->
                <div class="ipo-card">
                    <h4><i class="fas fa-file-invoice-dollar"></i> 재무 요약 <small>(백만원)</small></h4>
                    <div class="financial-item">
                        <span class="financial-label">매출액</span>
                        <span class="financial-value">${(it.revenue || 0).toLocaleString()}</span>
                    </div>
                    <div class="financial-item">
                        <span class="financial-label">법인세차감전이익</span>
                        <span class="financial-value">${(it.ebt || 0).toLocaleString()}</span>
                    </div>
                    <div class="financial-item">
                        <span class="financial-label">순이익</span>
                        <span class="financial-value" style="color:${(it.net_income || 0) >= 0 ? '#4ade80' : '#f87171'}">${(it.net_income || 0).toLocaleString()}</span>
                    </div>
                    <div class="financial-item">
                        <span class="financial-label">자본금</span>
                        <span class="financial-value">${(it.capital || 0).toLocaleString()}</span>
                    </div>
                </div>

                <!-- 카드 2: 공모 및 배정 정보 -->
                <div class="ipo-card">
                    <h4><i class="fas fa-coins"></i> 공모 및 배정</h4>
                    <div class="financial-item">
                        <span class="financial-label">총공모주식수</span>
                        <span class="financial-value">${(it.total_offer_shares || 0).toLocaleString()} <small>주</small></span>
                    </div>
                    <div class="financial-item">
                        <span class="financial-label">우리사주조합</span>
                        <span class="financial-value">${(it.employee_shares || 0).toLocaleString()} <small>주</small></span>
                    </div>
                    <div class="financial-item">
                        <span class="financial-label">기관투자자</span>
                        <span class="financial-value">${(it.inst_shares || 0).toLocaleString()} <small>주</small></span>
                    </div>
                    <div class="financial-item">
                        <span class="financial-label">일반청약자</span>
                        <span class="financial-value">${(it.retail_shares || 0).toLocaleString()} <small>주</small></span>
                    </div>
                </div>

                <!-- 카드 3: 발행 조건 및 수급 -->
                <div class="ipo-card">
                    <h4><i class="fas fa-chart-pie"></i> 발행 조건 및 수급</h4>
                    <div class="financial-item">
                        <span class="financial-label">액면가 / 희망가</span>
                        <span class="financial-value" style="font-size:0.8rem;">${(it.face_value || 0).toLocaleString()} / ${it.hope_price || '-'}</span>
                    </div>
                    <div class="financial-item">
                        <span class="financial-label">공모금액</span>
                        <span class="financial-value" style="color:#facc15;">${(it.offer_amount || 0).toLocaleString()} <small>백만</small></span>
                    </div>
                    <div class="financial-item">
                        <span class="financial-label">유통물량 (%)</span>
                        <span class="financial-value" style="color:${(it.float_shares_pct || 0) < 20 ? '#facc15' : '#e2e8f0'}">${it.float_shares_pct || 0}%</span>
                    </div>
                    <div class="financial-item">
                        <span class="financial-label">유통물량 (주)</span>
                        <span class="financial-value" style="font-size:0.8rem;">${(it.float_shares_vol || 0).toLocaleString()} <small>주</small></span>
                    </div>
                </div>

                <!-- 카드 4: 상장 당일 성과 -->
                <div class="ipo-card">
                    <h4><i class="fas fa-history"></i> 상장 당일 성과</h4>
                    <div class="price-detail-group">
                        <div class="price-row">
                            <span class="price-label">시가 (수익률)</span>
                            <span class="price-val ${openRet >= 0 ? 'up' : 'down'}">${(it.listing_day_open || 0).toLocaleString()} <small>(${openRet >= 0 ? '+' : ''}${openRet.toFixed(1)}%)</small></span>
                        </div>
                        <div class="price-row">
                            <span class="price-label">고가 (수익률)</span>
                            <span class="price-val up">${(it.listing_day_high || 0).toLocaleString()} <small>(+${highRet.toFixed(1)}%)</small></span>
                        </div>
                        <div class="price-row" style="margin-top:5px; border-top:1px solid rgba(255,255,255,0.05); padding-top:5px;">
                            <span class="price-label">종가 (최종)</span>
                            <span class="price-val ${it.listing_day_change_pct >= 0 ? 'up' : 'down'}" style="font-size:1rem;">${(it.listing_day_close || 0).toLocaleString()} <small>(${it.listing_day_change_pct >= 0 ? '+' : ''}${(it.listing_day_change_pct || 0).toFixed(1)}%)</small></span>
                        </div>
                    </div>
                </div>
            </div>
            
            <div style="margin-top:15px; display:flex; justify-content:space-between; align-items:center;">
                <div style="font-size:0.8rem; color:#64748b;">
                    <i class="fas fa-university"></i> 주간사: ${it.lead_manager || '-'}
                </div>
                <div style="display:flex; gap:10px; align-items:center;">
                    ${actionButtons}
                    ${it.ticker ? `<a href="/stock/${it.ticker}" onclick="event.preventDefault(); window._jumpToStock('${it.ticker}', '${it.name}')" class="stats-btn-action stats-btn-stock"><i class="fas fa-search-dollar"></i> 종목 분석</a>` : ''}
                    <a href="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" target="_blank" class="stats-btn-action stats-btn-dart" style="opacity:0.5; pointer-events:none;">DART 원문 <i class="fas fa-external-link-alt"></i></a>
                </div>
            </div>
        `;
    },

    /**
     * 상세 보기 행 내부의 동적 조작 버튼 이벤트를 바인딩합니다.
     */
    bindDetailRowEvents: function (container, it) {
        const btnAssign = container.querySelector('.btn-assign');
        if (btnAssign) {
            btnAssign.onclick = () => {
                this.showAssignModal(it.ticker, it.name);
            };
        }

        const btnIgnore = container.querySelector('.btn-ignore');
        if (btnIgnore) {
            btnIgnore.onclick = async () => {
                if (confirm(`종목 [${it.name}]을 대기 목록에서 제외하시겠습니까?`)) {
                    try {
                        const res = await fetch(`/api/stock/delete?board=virtual_신규상장주&ticker=${it.ticker}`, { method: 'DELETE' });
                        if (res.ok) {
                            alert('대기 목록에서 제외되었습니다.');
                            await this.loadData();
                        } else {
                            throw new Error('API request failed');
                        }
                    } catch (e) {
                        alert(`제외 처리 중 오류 발생: ${e.message}`);
                    }
                }
            };
        }

        const btnJump = container.querySelector('.btn-jump');
        if (btnJump) {
            btnJump.onclick = () => {
                const board = btnJump.dataset.board;
                if (window._jumpToBoard) {
                    window._jumpToBoard(board);
                } else {
                    alert(`마인드맵 탭으로 이동하여 보드 '${board}'를 직접 선택하세요.`);
                }
            };
        }
    },

    /**
     * 테마 보드 배치 모달 윈도우를 출력하고 API 연동을 수행합니다.
     */
    showAssignModal: async function (ticker, name) {
        // 기존 덮어쓰기 모달 제거
        const existing = document.getElementById('ipo-assign-modal-overlay');
        if (existing) existing.remove();

        const overlay = document.createElement('div');
        overlay.id = 'ipo-assign-modal-overlay';
        overlay.className = 'ipo-modal-overlay';
        overlay.innerHTML = `
            <div class="ipo-modal">
                <h3><i class="fas fa-th-large" style="color:#3b82f6;"></i> 신규상장주 보드 배치</h3>
                <p style="font-size:0.85rem; color:#94a3b8; margin-bottom:15px;">
                    종목 <strong>[${name} (${ticker})]</strong>을(를) 마인드맵 보드에 할당합니다.
                </p>
                
                <div class="ipo-modal-field">
                    <label>대상 테마 보드 (1뎁스)</label>
                    <select id="ipo-board-select" class="ipo-modal-select">
                        <option value="">보드를 불러오는 중...</option>
                    </select>
                </div>
                
                <!-- 동적 하위 노드 선택상자들이 추가될 영역 -->
                <div id="ipo-dynamic-fields-container"></div>

                <!-- 현재 실시간 선택 경로 표시 영역 -->
                <div id="ipo-current-path-wrapper" style="margin-top:15px; display:none;">
                    <label style="display:block; font-size:0.8rem; color:#94a3b8; margin-bottom:5px;">배치될 최종 위치 경로</label>
                    <div id="ipo-current-path" style="font-size:0.85rem; color:#3b82f6; font-weight:600; padding:10px; background:#0f172a; border-radius:8px; border:1px solid rgba(255,255,255,0.05); word-break:break-all; display:flex; align-items:center; gap:5px; flex-wrap:wrap;">
                        (선택되지 않음)
                    </div>
                </div>
                
                <div class="ipo-modal-footer">
                    <button id="ipo-btn-cancel" class="ipo-modal-btn cancel">취소</button>
                    <button id="ipo-btn-confirm" class="ipo-modal-btn confirm" disabled>배치 확정</button>
                </div>
            </div>
        `;

        document.body.appendChild(overlay);

        const boardSelect = document.getElementById('ipo-board-select');
        const dynamicContainer = document.getElementById('ipo-dynamic-fields-container');
        const pathWrapper = document.getElementById('ipo-current-path-wrapper');
        const pathDiv = document.getElementById('ipo-current-path');
        const confirmBtn = document.getElementById('ipo-btn-confirm');
        const cancelBtn = document.getElementById('ipo-btn-cancel');

        let treeData = null;
        let levels = []; // { parentNode, selectEl, fieldDiv } 배열

        // 모달 닫기 함수
        const closeModal = () => overlay.remove();
        cancelBtn.onclick = closeModal;
        overlay.onclick = (e) => { if (e.target === overlay) closeModal(); };

        // 현재 실시간 선택된 경로와 최종 노드 타겟을 계산하여 UI 업데이트 및 확정 활성화
        const updateCurrentPath = () => {
            const boardName = boardSelect.options[boardSelect.selectedIndex].text;
            let pathSegments = [boardName];
            let lastSelectedNode = treeData ? treeData.name : null;

            for (let i = 0; i < levels.length; i++) {
                const val = levels[i].selectEl.value;
                if (val) {
                    pathSegments.push(val);
                    lastSelectedNode = val;
                } else {
                    break;
                }
            }

            if (lastSelectedNode) {
                pathWrapper.style.display = 'block';
                pathDiv.innerHTML = `<i class="fas fa-folder-open" style="color:#facc15; margin-right:5px;"></i> ${pathSegments.join(' <i class="fas fa-chevron-right" style="font-size:0.7rem;color:#64748b;margin:0 3px;"></i> ')}`;
                confirmBtn.disabled = false; // 중간 섹터에도 삽입 가능하므로 루트 이상 선택되면 언제든 확정 가능
                confirmBtn.dataset.targetNode = lastSelectedNode;
            } else {
                pathWrapper.style.display = 'none';
                confirmBtn.disabled = true;
            }
        };

        // 하위 자식이 존재하는지 확인하고, 있으면 다음 뎁스의 선택 상자를 생성하는 함수
        const createNextLevel = (parentNode, depth) => {
            if (!parentNode.nodes || parentNode.nodes.length === 0) {
                updateCurrentPath();
                return;
            }

            const fieldDiv = document.createElement('div');
            fieldDiv.className = 'ipo-modal-field';
            fieldDiv.style.marginTop = '12px';
            fieldDiv.innerHTML = `
                <label style="display:block; font-size:0.8rem; color:#94a3b8; margin-bottom:5px;">배치할 하위 섹터 (${depth + 2}뎁스)</label>
                <select class="ipo-modal-select" id="ipo-select-level-${depth}">
                    <option value="">-- 하위 섹터 선택 (선택 사항) --</option>
                </select>
            `;

            dynamicContainer.appendChild(fieldDiv);

            const selectEl = fieldDiv.querySelector('select');
            parentNode.nodes.forEach(child => {
                const opt = document.createElement('option');
                opt.value = child.name;
                opt.textContent = child.name;
                selectEl.appendChild(opt);
            });

            levels.push({ parentNode, selectEl, fieldDiv });

            selectEl.onchange = () => {
                // 현재보다 더 깊은 레벨의 선택 박스들 제거
                while (levels.length > depth + 1) {
                    const removed = levels.pop();
                    removed.fieldDiv.remove();
                }

                const selectedVal = selectEl.value;
                if (selectedVal) {
                    const nextNode = parentNode.nodes.find(n => n.name === selectedVal);
                    if (nextNode) {
                        createNextLevel(nextNode, depth + 1);
                    }
                } else {
                    updateCurrentPath();
                }
            };

            updateCurrentPath();
        };

        try {
            // 1. 보드 목록 로드
            const resBoards = await fetch('/api/boards');
            const boards = await resBoards.json();
            
            // theme_* 보드만 필터링
            const themeBoards = boards.filter(b => b.id.startsWith('theme_'));
            
            boardSelect.innerHTML = '<option value="">-- 보드 선택 --</option>';
            themeBoards.forEach(b => {
                const opt = document.createElement('option');
                opt.value = b.id;
                opt.textContent = b.name;
                boardSelect.appendChild(opt);
            });

            // 2. 보드 선택 이벤트 바인딩
            boardSelect.onchange = async () => {
                const selectedBoard = boardSelect.value;
                dynamicContainer.innerHTML = '';
                pathWrapper.style.display = 'none';
                confirmBtn.disabled = true;
                levels = [];
                treeData = null;

                if (!selectedBoard) return;

                try {
                    const resTree = await fetch(`/api/board?name=${selectedBoard}`);
                    treeData = await resTree.json();
                    
                    // 보드의 루트 노드 하위(2뎁스) 탐색기 띄우기
                    createNextLevel(treeData, 0);
                } catch (e) {
                    console.error(e);
                    dynamicContainer.innerHTML = '<div style="color:#ef4444;font-size:0.8rem;margin-top:10px;">보드 노드 정보를 불러오지 못했습니다.</div>';
                }
            };

            // 3. 배치 확정 처리
            confirmBtn.onclick = async () => {
                const selectedBoard = boardSelect.value;
                const selectedNode = confirmBtn.dataset.targetNode;
                if (!selectedNode) return;
                
                confirmBtn.disabled = true;
                confirmBtn.textContent = '배치 중...';

                try {
                    // Step 1: 가상보드 대기목록에서 제거
                    const delRes = await fetch(`/api/stock/delete?board=virtual_신규상장주&ticker=${ticker}`, { method: 'DELETE' });
                    if (!delRes.ok) throw new Error('가상보드 제거 실패');

                    // Step 2: 타겟 보드에 추가 (동시에 백엔드 훅이 매니페스트 ASSIGNED 갱신 및 Gdrive 싱크 실행)
                    const addRes = await fetch(`/api/stock/add?board=${selectedBoard}&parent=${encodeURIComponent(selectedNode)}&name=${encodeURIComponent(name)}&ticker=${ticker}`, { method: 'POST' });
                    if (!addRes.ok) throw new Error('테마 보드 추가 실패');

                    alert(`종목 [${name}]이 [${boardSelect.options[boardSelect.selectedIndex].text} > ${selectedNode}] 보드에 성공적으로 배치되었습니다.`);
                    closeModal();
                    await this.loadData();
                } catch (err) {
                    alert(`배치 오류: ${err.message}`);
                    confirmBtn.disabled = false;
                    confirmBtn.textContent = '배치 확정';
                }
            };

        } catch (e) {
            boardSelect.innerHTML = '<option value="">board load failed</option>';
            console.error(e);
        }
    },

    /**
     * 렌더링 후 종목 링크 등 이벤트 바인딩
     */
    bindEventsAfterRender: function (container) {
        container.querySelectorAll('.stock-link').forEach(el => {
            el.addEventListener('click', (e) => {
                const ticker = e.currentTarget.dataset.ticker;
                const name = e.currentTarget.dataset.name;
                if (ticker && ticker !== 'none') {
                    window._jumpToStock(ticker, name);
                } else {
                    alert(`종목 [${name}]의 티커 정보를 찾을 수 없습니다.`);
                }
            });
        });
    }
};
