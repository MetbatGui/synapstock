/**
 * @fileoverview 탭 전환, 로그 콘솔, History API, 재무 사이드바 UI 모듈.
 * @module ui/tabs
 */

/**
 * 로그 타입을 나타내는 문자열 리터럴 타입.
 *
 * @typedef {'info'|'success'|'error'|'system'} LogType
 */

/**
 * 로그 콘솔(`#log-console`)에 타임스탬프와 함께 메시지를 추가합니다.
 *
 * 새 항목 추가 후 콘솔을 자동으로 하단으로 스크롤합니다.
 *
 * @param {string} message - 표시할 메시지 내용.
 * @param {LogType=} type - 로그 타입. CSS 클래스로 적용됩니다. 기본값은 `'info'`.
 * @returns {void}
 */
export function addLogEntry(message, type = 'info') {
    const consoleEl = document.getElementById('log-console');
    if (!consoleEl) return;

    const entry = document.createElement('div');
    entry.className = `log-entry ${type}`;

    const time = new Date().toLocaleTimeString();
    entry.innerText = `[${time}] ${message}`;

    consoleEl.appendChild(entry);
    consoleEl.scrollTop = consoleEl.scrollHeight;
}

/**
 * 내비게이션 탭 버튼(`.nav-item`)에 클릭 이벤트를 바인딩하여 탭 전환을 초기화합니다.
 *
 * @returns {void}
 */
export function initTabs() {
    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const targetTab = item.getAttribute('data-tab');
            switchTab(targetTab, true);
        });
    });
}

/**
 * 지정된 탭으로 전환하고 필요에 따라 URL History를 업데이트합니다.
 *
 * 활성 탭 버튼(`.nav-item`)과 콘텐츠 영역(`.tab-content`)의 `active` 클래스를 갱신합니다.
 * `dashboard-tab` 이외의 탭으로 전환 시 재무 사이드바를 자동으로 닫습니다.
 *
 * @param {string} tabId - 전환할 탭의 HTML `id`.
 * @param {boolean=} updateHistory - `true`이면 `history.pushState`로 URL을 변경합니다. 기본값은 `true`.
 * @returns {void}
 */
export function switchTab(tabId, updateHistory = true) {
    document.querySelectorAll('.nav-item').forEach(btn => {
        btn.classList.remove('active');
        if (btn.getAttribute('data-tab') === tabId) btn.classList.add('active');
    });

    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
        if (tab.id === tabId) tab.classList.add('active');
    });

    if (updateHistory) {
        if (tabId === 'mindmap-tab') {
            history.pushState({ tab: 'mindmap' }, '', '/');
        } else if (tabId === 'dashboard-tab' && !window.location.pathname.startsWith('/stock/')) {
            history.pushState({ tab: 'dashboard' }, '', '/stock/none');
        } else if (tabId === 'statistics-tab') {
            history.pushState({ tab: 'statistics' }, '', '/statistics');
        }
    }

    const financialToggle = document.getElementById('toggle-financial-sidebar');
    const financialSidebar = document.getElementById('financial-sidebar');
    if (financialToggle && financialSidebar) {
        if (tabId === 'dashboard-tab') {
            financialToggle.classList.add('active-tab');
            financialSidebar.classList.add('active-tab');
        } else {
            financialToggle.classList.remove('active-tab');
            financialSidebar.classList.remove('active-tab');
            financialSidebar.classList.remove('open');
            financialToggle.classList.remove('sidebar-open');
            financialToggle.style.right = '0';
        }
    }
}

/**
 * `popstate` 이벤트를 감지하여 브라우저 뒤로가기/앞으로가기 시 올바른 탭과 데이터를 로드합니다.
 *
 * @param {function(string, string|null): void} loadStockDashboard
 *     종목 대시보드를 로드하는 함수. 첫 번째 인자는 티커, 두 번째는 종목명(없으면 `null`).
 * @returns {void}
 */
export function initHistoryState(loadStockDashboard) {
    window.addEventListener('popstate', (event) => {
        const path = window.location.pathname;
        if (path === '/') {
            switchTab('mindmap-tab', false);
        } else if (path.startsWith('/stock/')) {
            const ticker = path.split('/').pop();
            const name = event.state ? event.state.name : null;
            switchTab('dashboard-tab', false);
            loadStockDashboard(ticker, name);
        }
    });
}

/**
 * 재무 사이드바(`#financial-sidebar`)의 토글 및 닫기 버튼 이벤트를 초기화합니다.
 *
 * @returns {void}
 */
export function initFinancialSidebar() {
    const sidebar = document.getElementById('financial-sidebar');
    const toggleBtn = document.getElementById('toggle-financial-sidebar');
    const closeBtn = document.getElementById('close-financial-sidebar');

    if (toggleBtn) {
        toggleBtn.onclick = () => {
            sidebar.classList.toggle('open');
            toggleBtn.classList.toggle('sidebar-open');
        };
    }

    if (closeBtn) {
        closeBtn.onclick = () => {
            sidebar.classList.remove('open');
            toggleBtn.classList.remove('sidebar-open');
        };
    }
}
