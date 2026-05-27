/**
 * @fileoverview 주식 분할(액면분할) 분석 뷰 모듈.
 *
 * 구글 드라이브에서 동기화된 주식 분할(액면분할) 결정 공시 데이터를
 * 테이블 형식으로 표시하고, 분할 비율·기준일·신주 상장일 등의 핵심
 * 일정을 관리합니다.
 */

export const stockSplitView = {
    /**
     * 액면분할 분석 뷰를 렌더링합니다.
     * @param {HTMLElement} container - 렌더링될 대상 컨테이너.
     */
    render: async function (container) {
        this.mainContainer = container;
        container.innerHTML = `
            <div class="stats-container stats-narrow animate-fade-in">
                <div class="stats-header">
                    <h2><i class="fas fa-cut"></i> 주식 분할(액면분할) 분석</h2>
                    <div class="stats-filters">
                        <select id="ss-year-select" class="stats-select" title="연도 선택">
                            <option value="all">전체 연도</option>
                        </select>
                        <button id="sync-stock-split-btn" class="stats-btn-refresh" title="최신 데이터 동기화">
                            <i class="fas fa-sync-alt"></i>
                        </button>
                    </div>
                </div>

                <div class="stats-table-wrapper">
                    <table class="stats-table" id="stock-split-table">
                        <thead>
                            <tr>
                                <th style="width: 140px;">기준일</th>
                                <th>종목명</th>
                                <th style="width: 90px; text-align:center;">시장</th>
                                <th style="width: 130px; text-align:right;">분할비율</th>
                                <th style="width: 180px; text-align:right;">발행주식(이전)</th>
                                <th style="width: 180px; text-align:right;">발행주식(이후)</th>
                                <th style="width: 140px; text-align:right;">신주상장예정일</th>
                                <th style="width: 70px; text-align:center;">상세</th>
                            </tr>
                        </thead>
                        <tbody id="stock-split-tbody">
                            <tr><td colspan="8" class="stats-loader">데이터를 불러오는 중...</td></tr>
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
        const syncBtn = document.getElementById('sync-stock-split-btn');
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

        const yearSelect = document.getElementById('ss-year-select');
        if (yearSelect) {
            yearSelect.onchange = () => {
                this.renderTable(this.cachedItems, yearSelect.value);
            };
        }
    },

    cachedItems: [],

    /**
     * 서버로부터 주식 분할 데이터를 가져옵니다.
     * @param {boolean} forceSync - 강제 동기화 여부
     */
    loadData: async function (forceSync = false) {
        try {
            const response = await fetch(`/api/statistics/stock-splits?force_sync=${forceSync}`);
            const data = await response.json();
            const items = data.items || [];

            // 최신순 정렬 (배정기준일 기준)
            items.sort((a, b) => {
                const dateA = a.base_date || '';
                const dateB = b.base_date || '';
                return dateB.localeCompare(dateA);
            });

            this.cachedItems = this.calculateCorrectionOrders(items);
            this.updateYearOptions(items);

            const yearSelect = document.getElementById('ss-year-select');
            this.renderTable(this.cachedItems, yearSelect ? yearSelect.value : 'all');

        } catch (err) {
            console.error('Failed to load stock split data:', err);
            const tbody = document.getElementById('stock-split-tbody');
            if (tbody) tbody.innerHTML = `<tr><td colspan="8" class="stats-error">데이터 로드 실패: ${err.message}</td></tr>`;
        }
    },

    updateYearOptions: function (items) {
        const yearSelect = document.getElementById('ss-year-select');
        if (!yearSelect) return;

        const currentValue = yearSelect.value;
        yearSelect.innerHTML = '<option value="all">전체 연도</option>';

        const years = [...new Set(items.map(item => {
            const d = item.base_date || '';
            return d.substring(0, 4);
        }))].filter(y => y && y.length === 4).sort((a, b) => b.localeCompare(a));

        years.forEach(year => {
            const option = document.createElement('option');
            option.value = year;
            option.textContent = `${year}년`;
            yearSelect.appendChild(option);
        });

        // 현재 연도 기본 선택
        const thisYear = new Date().getFullYear().toString();
        if (years.includes(thisYear)) {
            yearSelect.value = thisYear;
        } else if (currentValue && years.includes(currentValue)) {
            yearSelect.value = currentValue;
        } else if (years.length > 0) {
            yearSelect.value = years[0];
        }
    },

    renderTable: function (items, selectedYear) {
        const tbody = document.getElementById('stock-split-tbody');
        if (!tbody) return;

        if (!items || items.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="stats-empty">데이터가 없습니다.</td></tr>';
            return;
        }

        let filteredItems = items;
        if (selectedYear && selectedYear !== 'all') {
            filteredItems = items.filter(item => {
                const date = item.base_date || '';
                return date.startsWith(selectedYear);
            });
        }

        if (filteredItems.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="stats-empty">해당 연도의 데이터가 없습니다.</td></tr>';
            return;
        }

        tbody.innerHTML = '';
        filteredItems.forEach((item) => {
            const tr = document.createElement('tr');
            tr.className = 'ss-row';
            tr.dataset.rcpNo = item.rcp_no || item.receipt_no;
            tr.style.cursor = 'pointer';

            const splitRatioHtml = item.split_ratio
                ? `<span style="font-weight:700; color:#4ade80;">1 : ${item.split_ratio.toFixed(1)}</span>`
                : '<span style="color:#9ca3af;">-</span>';

            const marketBadgeColor = item.market === 'KOSPI'
                ? 'background: rgba(96,165,250,0.15); color: #60a5fa; border: 1px solid rgba(96,165,250,0.3);'
                : 'background: rgba(167,139,250,0.15); color: #a78bfa; border: 1px solid rgba(167,139,250,0.3);';

            const marketBadge = item.market
                ? `<span style="font-size:0.7rem; padding:2px 6px; border-radius:4px; ${marketBadgeColor}">${item.market}</span>`
                : '-';

            const isCorrectionBadge = item.is_correction
                ? `<span style="font-size:0.7rem; background:#ef4444; color:white; padding:1px 4px; border-radius:3px; margin-left:5px;">정정</span>`
                : '';

            tr.innerHTML = `
                <td style="color:#9ca3af;">${item.base_date || '-'}</td>
                <td style="font-weight:600; color:#e5e7eb;">
                    ${item.company_name}
                    ${isCorrectionBadge}
                </td>
                <td style="text-align:center;">${marketBadge}</td>
                <td style="text-align:right;">${splitRatioHtml}</td>
                <td style="text-align:right; color:#9ca3af;">${item.prev_shares ? item.prev_shares.toLocaleString() : '-'}</td>
                <td style="text-align:right; color:#e5e7eb;">${item.post_shares ? item.post_shares.toLocaleString() : '-'}</td>
                <td style="text-align:right; color:#facc15;">${item.listing_date || '-'}</td>
                <td style="text-align:center;">
                    <span class="expand-icon" style="color:var(--accent-blue); display: inline-block; transition: transform 0.2s;">▼</span>
                </td>
            `;

            const detailTr = document.createElement('tr');
            detailTr.className = 'detail-row';
            detailTr.style.display = 'none';
            detailTr.innerHTML = `<td colspan="8" class="detail-container"></td>`;

            tbody.appendChild(tr);
            tbody.appendChild(detailTr);

            tr.onclick = (e) => {
                if (e.target.closest('a')) return;

                const detailContainer = detailTr.querySelector('.detail-container');
                const icon = tr.querySelector('.expand-icon');
                const isHidden = detailTr.style.display === 'none';

                if (isHidden) {
                    // 다른 열려있는 상세 행 닫기
                    tbody.querySelectorAll('.detail-row').forEach(row => {
                        row.style.display = 'none';
                        row.classList.remove('expanded');
                    });
                    tbody.querySelectorAll('.expand-icon').forEach(ic => ic.style.transform = 'rotate(0deg)');

                    if (detailContainer.innerHTML.trim().length < 50) {
                        detailContainer.innerHTML = this.generateDetailHtml(item);
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

    generateDetailHtml: function (item) {
        const splitRatioStr = item.split_ratio
            ? `1 : ${item.split_ratio.toFixed(1)} (${item.split_ratio}배 분할)`
            : '-';

        return `
            <div class="stats-detail-container animate-fade-in">
                <div class="stats-detail-grid">
                    <!-- 왼쪽 카드: 분할 개요 -->
                    <div class="stats-card">
                        <h4 style="margin-top:0; color:var(--accent-blue); border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 8px; margin-bottom: 12px;">
                            <i class="fas fa-info-circle"></i> 주식 분할 개요
                        </h4>
                        <div style="display: flex; flex-direction: column; gap: 12px; margin-top: 5px;">
                            <div style="display: flex; justify-content: space-between; align-items: baseline;">
                                <span style="color: #9ca3af;">분할비율</span>
                                <span style="font-size: 1.25rem; font-weight: 700; color: #4ade80;">${splitRatioStr}</span>
                            </div>
                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 10px;">
                                <div style="display: flex; flex-direction: column; gap: 4px;">
                                    <span style="color: #9ca3af; font-size: 0.8rem;">발행주식수 (이전)</span>
                                    <span style="font-weight: 600; color:#9ca3af;">${item.prev_shares ? item.prev_shares.toLocaleString() + ' 주' : '-'}</span>
                                </div>
                                <div style="display: flex; flex-direction: column; gap: 4px;">
                                    <span style="color: #9ca3af; font-size: 0.8rem;">발행주식수 (이후)</span>
                                    <span style="font-weight: 700; color:#e5e7eb;">${item.post_shares ? item.post_shares.toLocaleString() + ' 주' : '-'}</span>
                                </div>
                            </div>
                            <div style="display: flex; justify-content: space-between; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 10px;">
                                <span style="color: #9ca3af;">공시 구분</span>
                                <span style="font-weight: 600;">${item.disclosure_type || '-'}</span>
                            </div>
                            <div style="display: flex; justify-content: space-between;">
                                <span style="color: #9ca3af;">시장</span>
                                <span style="font-weight: 600;">${item.market || '-'}</span>
                            </div>
                        </div>
                    </div>

                    <!-- 오른쪽 카드: 주요 일정 -->
                    <div class="stats-card">
                        <h4 style="margin-top:0; color:var(--accent-blue); border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 8px; margin-bottom: 15px;">
                            <i class="fas fa-calendar-alt"></i> 주요 일정
                        </h4>
                        <div class="stats-timeline">
                            ${item.first_disclosure_date ? `
                            <div class="stats-timeline-item">
                                <div style="color: #9ca3af;">최초공시 등록일</div>
                                <div class="stats-timeline-date">${item.first_disclosure_date}</div>
                            </div>` : ''}
                            <div class="stats-timeline-item">
                                <div style="color: #9ca3af;">이사회결의일</div>
                                <div class="stats-timeline-date">${item.board_resolution_date || '-'}</div>
                            </div>
                            ${item.general_meeting_date ? `
                            <div class="stats-timeline-item">
                                <div style="color: #9ca3af;">주총결의일</div>
                                <div class="stats-timeline-date">${item.general_meeting_date}</div>
                            </div>` : ''}
                            <div class="stats-timeline-item active">
                                <div style="color: #9ca3af;">등록일자 (기준일)</div>
                                <div class="stats-timeline-date">${item.base_date || '-'}</div>
                            </div>
                            <div class="stats-timeline-item">
                                <div style="color: #9ca3af;">신주 상장예정일</div>
                                <div class="stats-timeline-date" style="color: #facc15;">${item.listing_date || '-'}</div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- 하단 정보 및 액션 버튼 -->
                <div class="stats-info-footer">
                    <div style="margin-right: auto; font-size: 0.85rem; color: #9ca3af;">
                        <i class="fas fa-fingerprint"></i> 접수번호: ${item.rcp_no || item.receipt_no}
                        ${item.parent_rcp_no ? `<br/><i class="fas fa-link"></i> 원접수번호: ${item.parent_rcp_no}` : ''}
                    </div>
                    <div style="display: flex; gap: 10px;">
                        <a href="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${item.rcp_no || item.receipt_no}" target="_blank" class="stats-btn-action stats-btn-dart">
                            DART 공시 원문 보기 <i class="fas fa-external-link-alt"></i>
                        </a>
                    </div>
                </div>
            </div>
        `;
    },

    /**
     * 정정 공시 횟수를 계산하여 각 아이템에 correction_count를 추가합니다.
     * @param {Array} items - 원시 데이터 배열
     * @returns {Array} correction_count가 추가된 배열
     */
    calculateCorrectionOrders: function (items) {
        if (!items || items.length === 0) return [];
        const itemMap = {};
        items.forEach(item => {
            const key = item.rcp_no || item.receipt_no;
            if (key) itemMap[key] = item;
        });

        return items.map(item => {
            let count = 0;
            let current = item;
            while (current && current.parent_rcp_no && itemMap[current.parent_rcp_no]) {
                count++;
                current = itemMap[current.parent_rcp_no];
                if ((current.rcp_no || current.receipt_no) === (item.rcp_no || item.receipt_no)) break;
            }
            return { ...item, correction_count: count };
        });
    },
};
