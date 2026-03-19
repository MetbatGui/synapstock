/**
 * SynapStock Frontend Logic
 * SPA Tab Switching, Tree Rendering, WebSocket Logs, History API
 */

document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initTree();
    initWebSocket();
    initSyncButton();
    initHistoryState();

    // URL을 파싱하여 초기 상태 설정 (SPA 경로 지원)
    // /stock/{ticker} 형식의 URL에서 티커를 추출하여 대시보드를 로드합니다.
    const path = window.location.pathname;
    if (path.startsWith('/stock/')) {
        const parts = path.split('/');
        const ticker = parts[parts.length - 1];
        if (ticker && ticker !== 'none') {
            switchTab('dashboard-tab', false); // URL 중복 방지를 위해 pushState는 false
            loadStockDashboard(ticker);
        }
    }
});

/**
 * 로그 콘솔에 메시지를 추가하는 공통 함수
 */
function addLogEntry(message, type = 'info') {
    const consoleEl = document.getElementById('log-console');
    if (!consoleEl) return;

    const entry = document.createElement('div');
    entry.className = `log-entry ${type}`;

    const time = new Date().toLocaleTimeString();
    entry.innerText = `[${time}] ${message}`;

    consoleEl.appendChild(entry);
    consoleEl.scrollTop = consoleEl.scrollHeight;
}

// 1. 탭 전환 로직
function initTabs() {
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
 * 탭 전환 및 URL 업데이트
 * @param {string} tabId - 전환할 탭 ID
 * @param {boolean} updateHistory - History API를 통해 URL을 변경할지 여부
 */
function switchTab(tabId, updateHistory = true) {
    // 버튼 상태 업데이트
    document.querySelectorAll('.nav-item').forEach(btn => {
        btn.classList.remove('active');
        if (btn.getAttribute('data-tab') === tabId) btn.classList.add('active');
    });

    // 콘텐츠 표시 업데이트
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
        if (tab.id === tabId) tab.classList.add('active');
    });

    // URL 업데이트 (주석: 마인드맵 탭으로 돌아올 때 URL을 /로 초기화)
    if (updateHistory) {
        if (tabId === 'mindmap-tab') {
            history.pushState({ tab: 'mindmap' }, '', '/');
        } else if (tabId === 'dashboard-tab' && !window.location.pathname.startsWith('/stock/')) {
            // 종목 정보 탭을 직접 눌렀을 때 (특정 종목 선택 전)
            history.pushState({ tab: 'dashboard' }, '', '/stock/none');
        }
    }
}

// 2. 트리 렌더링 로직
let currentBoardName = null;

async function initTree() {
    const boardSelect = document.getElementById('board-select');
    const loadBtn = document.getElementById('load-board-btn');
    const treeContainer = document.getElementById('tree-container');

    treeContainer.innerHTML = '<div class="tree-empty-state">왼쪽 상단에서 보드를 선택하고 [불러오기]를 눌러주세요.</div>';

    addLogEntry('[API] 사용 가능한 보드 목록을 조회 중입니다...', 'system');

    try {
        const boardsRes = await fetch('/api/boards');
        const boards = await boardsRes.json();

        boardSelect.innerHTML = '<option value="" disabled selected>보드를 선택하세요</option>';
        boards.forEach(name => {
            const option = document.createElement('option');
            option.value = name;
            option.textContent = name.replace('theme_', '');
            boardSelect.appendChild(option);
        });

        addLogEntry(`[API] 총 ${boards.length}개의 마인드맵 보드를 찾았습니다.`, 'success');

        loadBtn.addEventListener('click', () => {
            const selectedName = boardSelect.value;
            if (!selectedName || selectedName === "") {
                addLogEntry('[WARN] 불러올 보드를 선택해 주세요.', 'error');
                return;
            }
            currentBoardName = selectedName;
            loadBoardData(currentBoardName);
        });

    } catch (err) {
        addLogEntry(`[ERROR] 보드 목록 조회 실패: ${err.message}`, 'error');
    }
}

async function loadBoardData(name) {
    const treeContainer = document.getElementById('tree-container');
    treeContainer.innerHTML = '<div class="loading-shimmer">데이터를 불러오는 중...</div>';

    addLogEntry(`[API] 보드 데이터 요청: ${name}`, 'system');

    try {
        const response = await fetch(`/api/board?name=${name}`);
        if (!response.ok) throw new Error(`HTTP Error ${response.status}`);

        const data = await response.json();
        currentBoardData = data; // 전역 데이터 업데이트
        treeContainer.innerHTML = '';

        const rootList = document.createElement('div');
        rootList.className = 'tree-root';
        renderNode(data, rootList, 0);
        treeContainer.appendChild(rootList);

        updateStockCount(data);
        addLogEntry(`[API] '${name}' 보드 데이터를 성공적으로 로드했습니다.`, 'success');
    } catch (err) {
        addLogEntry(`[ERROR] '${name}' 로드 중 오류 발생: ${err.message}`, 'error');
        treeContainer.innerHTML = `<div class="error" style="color: #ef4444; padding: 20px; text-align: center;">데이터 로드 실패: ${err.message}</div>`;
    }
}

function renderNode(node, container, depth) {
    const nodeEl = document.createElement('div');
    nodeEl.className = 'tree-node';

    const header = document.createElement('div');
    // 빈 노드도 오버뷰 패널을 띄워 자식을 추가/삭제할 수 있도록 항상 폴더로 취급합니다.
    const isFolder = true;

    header.className = `node-header folder`;
    header.innerHTML = `<span class="node-title">${node.name}</span>`;

    const childrenContainer = document.createElement('div');
    childrenContainer.className = 'children-container';

    if (isFolder) {
        header.addEventListener('click', (e) => {
            e.stopPropagation();
            header.classList.toggle('expanded');
            childrenContainer.classList.toggle('show');

            // 노드 오버뷰 업데이트
            updateNodeOverview(node);
        });

        if (node.nodes) {
            node.nodes.forEach(child => renderNode(child, childrenContainer, depth + 1));
        }

        if (node.stocks) {
            node.stocks.forEach(stock => {
                const stockHeader = document.createElement('div');
                stockHeader.className = 'node-header stock';
                stockHeader.style.cursor = 'pointer'; // 명시적으로 클릭 가능 표시
                stockHeader.innerHTML = `<a href="#" class="tree-stock-link" onclick="event.preventDefault();">${stock.name} (${stock.ticker || 'N/A'})</a>`;

                const handleStockClick = (e) => {
                    e.preventDefault();
                    e.stopPropagation();

                    const ticker = stock.ticker;
                    const name = stock.name;

                    // 고정 오버뷰 패널 업데이트
                    const overviewPanel = document.getElementById('stock-overview-panel');
                    if (overviewPanel) {
                        overviewPanel.style.display = 'block';
                        overviewPanel.innerHTML = `
                                    <div class="overview-header">
                                        <h3>${name} (${ticker})</h3>
                                    </div>
                                    <div class="overview-stats">
                                        <div class="stat-item">📰 <span>뉴스</span> <span class="count">0</span></div>
                                        <div class="stat-item">📊 <span>리포트</span> <span class="count">0</span></div>
                                    </div>
                                    <div class="overview-footer">
                                        <button class="btn btn-primary btn-sm btn-go-detail" style="width: auto;">상세 이동</button>
                                    </div>
                                `;

                        // 상세 보기 버튼 연동
                        overviewPanel.querySelector('.btn-go-detail').onclick = () => {
                            addLogEntry(`[UI] 종목 상세로 이동: ${name}(${ticker})`, 'info');
                            history.pushState({ tab: 'dashboard', ticker: ticker, name: name }, '', `/stock/${ticker}`);
                            switchTab('dashboard-tab', false);
                            loadStockDashboard(ticker, name);
                        };
                    }

                    addLogEntry(`[UI] 종목 선택됨: ${name}(${ticker}) - 오버뷰 로드됨`, 'info');
                };

                stockHeader.addEventListener('click', handleStockClick);
                childrenContainer.appendChild(stockHeader);
            });
        }
    }

    nodeEl.appendChild(header);
    nodeEl.appendChild(childrenContainer);
    container.appendChild(nodeEl);

    if (depth < 1 && isFolder) {
        header.classList.add('expanded');
        childrenContainer.classList.add('show');
    }
}

function updateStockCount(root) {
    let count = countRecursiveStocks(root);
    const countEl = document.getElementById('total-stocks-count');
    if (countEl) countEl.innerText = count;
}

/**
 * 노드 클릭 시 우측 패널에 노드 정보 및 관리 버튼 표시
 */
function updateNodeOverview(node) {
    const overviewPanel = document.getElementById('stock-overview-panel');
    if (!overviewPanel) return;

    const subNodesCount = (node.nodes || []).length;
    const totalStocksCount = countRecursiveStocks(node);

    // 루트 노드인지 확인 (currentBoardData가 루트 노드 데이터를 들고 있음)
    const isRoot = currentBoardData && currentBoardData.name === node.name;

    overviewPanel.style.display = 'block';
    overviewPanel.innerHTML = `
        <div class="overview-header">
            <h3 style="color: #facc15 !important;">📁 ${node.name}</h3>
        </div>
        <div class="overview-stats">
            <div class="stat-item">🌿 <span>하위 노드</span> <span class="count">${subNodesCount}</span></div>
            <div class="stat-item">🚀 <span>전체 종목</span> <span class="count">${totalStocksCount}</span></div>
        </div>
        <div class="overview-footer" style="display: flex; gap: 10px; flex-wrap: wrap;">
            <button class="btn btn-secondary btn-sm" onclick="showAddNodeModal('${node.name}')">새 노드</button>
            <button class="btn btn-secondary btn-sm" onclick="showAddStockModal('${node.name}')">종목 추가</button>
            ${!isRoot ? `<button class="btn btn-danger btn-sm" onclick="deleteNode('${node.name}')" style="background: #ef4444; color: white;">제거</button>` : ''}
        </div>
    `;

    addLogEntry(`[UI] 노드 선택됨: ${node.name} (하위:${subNodesCount}, 종목:${totalStocksCount})`, 'info');
}

/**
 * 모달 열기/닫기 공통
 */
function openModal(id) {
    document.getElementById(id).classList.add('show');
}

function closeModal(id) {
    document.getElementById(id).classList.remove('show');
    if (id === 'add-stock-modal') {
        document.getElementById('autocomplete-results').style.display = 'none';
        document.getElementById('selected-stock-info').style.display = 'none';
        document.getElementById('confirm-add-stock').disabled = true;
        document.getElementById('stock-search-input').value = '';
    } else if (id === 'add-node-modal') {
        document.getElementById('new-node-name').value = '';
    }
}

// 글로벌 변수 (임시 저장용)
let LAST_CLICKED_NODE_NAME = '';
let SELECTED_STOCK = null;

function showAddNodeModal(parentName) {
    LAST_CLICKED_NODE_NAME = parentName;
    document.getElementById('parent-node-name').innerText = parentName;
    openModal('add-node-modal');
}

function showAddStockModal(targetName) {
    LAST_CLICKED_NODE_NAME = targetName;
    document.getElementById('target-node-name').innerText = targetName;
    openModal('add-stock-modal');
}

/**
 * 네이버 자동완성 API 연동
 */
document.addEventListener('DOMContentLoaded', () => {
    const searchInput = document.getElementById('stock-search-input');
    const resultsContainer = document.getElementById('autocomplete-results');

    if (searchInput) {
        searchInput.addEventListener('input', async (e) => {
            const query = e.target.value.trim();
            if (query.length < 2) {
                resultsContainer.style.display = 'none';
                return;
            }

            try {
                // 백엔드 프록시를 통해 네이버 자동완성 호출 (CORS 회피)
                const response = await fetch(`/api/stock/search?q=${encodeURIComponent(query)}`);
                const items = await response.json();

                if (items && items.length > 0) {
                    resultsContainer.innerHTML = '';
                    items.forEach(item => {
                        const div = document.createElement('div');
                        div.innerText = `${item.name} (${item.ticker})`;
                        div.onclick = () => {
                            SELECTED_STOCK = { name: item.name, ticker: item.ticker };
                            document.getElementById('selected-stock-display').innerText = `${SELECTED_STOCK.name} (${SELECTED_STOCK.ticker})`;
                            document.getElementById('selected-stock-info').style.display = 'block';
                            document.getElementById('confirm-add-stock').disabled = false;
                            resultsContainer.style.display = 'none';
                            searchInput.value = SELECTED_STOCK.name;
                        };
                        resultsContainer.appendChild(div);
                    });
                    resultsContainer.style.display = 'block';
                } else {
                    resultsContainer.style.display = 'none';
                }
            } catch (err) {
                console.error("Autocomplete failed:", err);
            }
        });
    }

    // 모달 확인 버튼들 초기화
    document.getElementById('confirm-add-node').onclick = async () => {
        const name = document.getElementById('new-node-name').value.trim();
        if (!name) return;

        const currentBoard = document.getElementById('board-select').value;
        const res = await fetch(`/api/node/add?board=${encodeURIComponent(currentBoard)}&parent=${encodeURIComponent(LAST_CLICKED_NODE_NAME)}&name=${encodeURIComponent(name)}`, { method: 'POST' });
        if (res.ok) {
            addLogEntry(`[SYSTEM] 노드 추가 성공: ${name}`, 'success');
            closeModal('add-node-modal');
            loadBoardData(currentBoardName); // 트리 갱신
        }
    };

    document.getElementById('confirm-add-stock').onclick = async () => {
        if (!SELECTED_STOCK) return;

        const currentBoard = document.getElementById('board-select').value;
        const res = await fetch(`/api/stock/add?board=${encodeURIComponent(currentBoard)}&parent=${encodeURIComponent(LAST_CLICKED_NODE_NAME)}&name=${encodeURIComponent(SELECTED_STOCK.name)}&ticker=${encodeURIComponent(SELECTED_STOCK.ticker)}`, { method: 'POST' });
        if (res.ok) {
            addLogEntry(`[SYSTEM] 종목 추가 성공: ${SELECTED_STOCK.name}`, 'success');
            closeModal('add-stock-modal');
            loadBoardData(currentBoardName); // 트리 갱신
        }
    };
});

async function deleteNode(nodeName) {
    if (!confirm(`'${nodeName}' 노드를 삭제하시겠습니까?\n하위 노드와 종목은 상위 노드로 흡수됩니다.`)) return;

    const currentBoard = document.getElementById('board-select').value;
    const res = await fetch(`/api/node/delete?board=${encodeURIComponent(currentBoard)}&name=${encodeURIComponent(nodeName)}`, { method: 'DELETE' });
    if (res.ok) {
        addLogEntry(`[SYSTEM] 노드 삭제 및 흡수 완료: ${nodeName}`, 'success');
        document.getElementById('stock-overview-panel').style.display = 'none';
        loadBoardData(currentBoardName);
    }
}

/**
 * 재귀적으로 하위 모든 종목 수를 계산
 */
function countRecursiveStocks(node) {
    let count = (node.stocks || []).length;
    if (node.nodes) {
        node.nodes.forEach(child => {
            count += countRecursiveStocks(child);
        });
    }
    return count;
}

// 3. 종목 대시보드 로드
let currentBoardData = null; // 전역 변수로 관리하여 이름 조회 등에 활용

function loadStockDashboard(ticker, name = null) {
    const container = document.getElementById('dashboard-container');
    const placeholder = document.getElementById('dashboard-placeholder');

    if (!ticker || ticker === 'none') {
        placeholder.style.display = 'flex';
        container.style.display = 'none';
        return;
    }

    // 이름이 없을 경우 백엔드 API에서 조회 시도
    if (!name) {
        // 즉시 UI를 그리고 나중에 이름을 업데이트하기 위해 별도 비동기 처리
        fetchStockInfo(ticker).then(info => {
            if (info && info.name) {
                const titleEl = document.querySelector('.dashboard-header h1');
                if (titleEl) titleEl.innerText = `${info.name}(${ticker})`;
                addLogEntry(`[UI] 종목명 확인: ${info.name}`, 'success');
            }
        });
    }

    const displayTitle = name ? `${name}(${ticker})` : ticker;

    placeholder.style.display = 'none';
    container.style.display = 'block';

    addLogEntry(`[UI] 종목 상세 조회: ${displayTitle}`, 'info');

    container.innerHTML = `
        <div class="card dashboard-card" style="padding: 40px; max-width: 1400px; margin: 0 auto;">
            <div class="dashboard-header" style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 25px;">
                <div>
                    <h1 style="font-size: 2.8rem; font-weight: 700; background: linear-gradient(90deg, #00d2ff, #9d50bb); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin: 0;">
                        ${displayTitle}
                    </h1>
                    <p style="color: #9ca3af; margin: 8px 0 0 0; font-size: 1rem;">Data Source: Naver Finance & DART</p>
                </div>
                <div style="text-align: right">
                    <span class="ticker-badge" style="background: rgba(0, 210, 255, 0.1); border: 1px solid #00d2ff; padding: 8px 20px; border-radius: 20px; color: #00d2ff; font-weight: 700; font-size: 1.1rem;">
                        ${ticker}
                    </span>
                </div>
            </div>
            
            <div class="dashboard-body" style="display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr); gap: 40px; margin-top: 35px;">
                <div class="left-column">
                    <div class="chart-section" style="background: rgba(0,0,0,0.2); border-radius: 24px; padding: 25px; text-align: center;">
                        <h3 style="margin-top: 0; margin-bottom: 15px; font-size: 1.2rem; color: #e5e7eb; font-weight: 600;">실시간 차트</h3>
                        <img src="https://ssl.pstatic.net/imgfinance/chart/item/area/day/${ticker}.png?v=${Date.now()}" 
                             style="width: 100%; max-width: 800px; border-radius: 16px; filter: invert(0.9) hue-rotate(180deg) brightness(1.1); margin-bottom: 20px; transition: transform 0.3s; cursor: zoom-in;"
                             onmouseover="this.style.transform='scale(1.02)'" onmouseout="this.style.transform='scale(1)'">
                        <div class="button-group" style="display: flex; justify-content: center; gap: 15px;">
                            <a href="https://finance.naver.com/item/main.naver?code=${ticker}" target="_blank" class="btn btn-naver" style="background: #03c75a; color: white; border: none; padding: 12px 30px; border-radius: 10px; font-weight: 700; text-decoration: none; display: inline-flex; align-items: center; gap: 8px; font-size: 1rem;">
                                <span style="font-size: 1.3rem;">N</span> 네이버 증권 홈
                            </a>
                        </div>
                    </div>
                </div>
                
                <div class="right-column" style="display: flex; flex-direction: column; gap: 20px; height: 100%;">
                    <div class="disclosure-section card" style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.05); padding: 25px; border-radius: 20px; display: flex; flex-direction: column; flex: 1;">
                        <h3 style="margin-top: 0; margin-bottom: 20px; font-size: 1.3rem; color: #00d2ff !important; display: flex; align-items: center; gap: 10px; font-weight: 700;">
                            <span>📋</span> 최근 DART 공시
                        </h3>
                        <div id="disclosure-list" class="disclosure-list" style="overflow-y: auto !important; flex: 1 !important;">
                            <div class="loading-mini" style="text-align: center; color: #9ca3af; padding: 30px;">공시 정보를 가져오는 중...</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;

    // 공시 정보 로드
    fetchDisclosures(ticker);
}

async function fetchDisclosures(ticker) {
    const listEl = document.getElementById('disclosure-list');
    if (!listEl) return;

    try {
        const response = await fetch(`/api/disclosure/${ticker}`);
        const data = await response.json();

        if (!data || data.length === 0) {
            listEl.innerHTML = '<div style="text-align: center; color: #6b7280; padding: 20px;">최근 1년 이내 공시가 없습니다.</div>';
            return;
        }

        listEl.innerHTML = ''; // Clear previous content
        data.forEach(item => {
            const entry = document.createElement('div');
            entry.className = 'disclosure-item';
            entry.innerHTML = `
                <a href="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${item.rcpNo}" 
                   target="_blank" class="disclosure-title" title="${item.title}" 
                   style="color: #e5e7eb !important; text-decoration: none !important; font-size: 0.95rem !important; display: block !important;">${item.title}</a>
                <span class="disclosure-date" style="color: #9ca3af !important; font-size: 0.85rem !important;">${item.date}</span>
            `;
            listEl.appendChild(entry);
        });

    } catch (err) {
        listEl.innerHTML = `<div style="text-align: center; color: #ef4444; padding: 20px;">로드 실패: ${err.message}</div>`;
    }
}

async function fetchStockInfo(ticker) {
    try {
        const response = await fetch(`/api/stock/info/${ticker}`);
        if (response.ok) return await response.json();
    } catch (err) {
        console.error("Failed to fetch stock info:", err);
    }
    return null;
}

// 4. History API & WebSocket & Sync 연동
function initHistoryState() {
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

function initWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const socket = new WebSocket(`${protocol}//${window.location.host}/ws/logs`);
    const progressBar = document.getElementById('sync-progress-bar');
    const statusIndicator = document.getElementById('sync-status-indicator');

    socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'log') {
            const isSuccess = data.message.includes('완료') || data.message.includes('성공');
            addLogEntry(data.message, isSuccess ? 'success' : 'info');

            progressBar.style.width = `${data.progress * 100}%`;

            if (data.progress >= 1.0) {
                statusIndicator.innerText = '● System Ready';
                statusIndicator.style.color = '#4ade80';
            } else {
                statusIndicator.innerText = '● Synchronizing...';
                statusIndicator.style.color = '#facc15';
            }
        }
    };

    socket.onopen = () => addLogEntry('[SYSTEM] 실시간 로그 서버에 연결되었습니다.', 'success');
}

function initSyncButton() {
    const syncBtn = document.getElementById('sync-btn');
    syncBtn.addEventListener('click', async () => {
        if (!currentBoardName) {
            addLogEntry('[WARN] 동기화할 보드가 로드되지 않았습니다.', 'error');
            return;
        }

        addLogEntry(`[API] Miro 동기화 요청: ${currentBoardName}...`, 'system');

        try {
            const response = await fetch(`/api/sync?name=${currentBoardName}`, { method: 'POST' });
            const data = await response.json();
            if (data.status === 'started') {
                addLogEntry(`[SYSTEM] '${currentBoardName}' 동기화 작업이 백그라운드에서 시작되었습니다.`, 'info');
            }
        } catch (err) {
            addLogEntry(`[ERROR] 동기화 요청 실패: ${err.message}`, 'error');
        }
    });
}
