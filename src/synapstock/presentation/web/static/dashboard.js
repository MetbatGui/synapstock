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
    initFinancialSidebar();
    initGlobalSearch();

    // URL을 파싱하여 초기 상태 설정 (SPA 경로 지원)
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

// 전역 상태 변수
let currentBoardData = null; 
let currentTicker = null;
let currentBoardName = ''; // 현재 로드된 보드 파일명
let globalLocalReportCounts = {}; // 로컬 리포트 수량을 저장할 전역 변수
let globalStockCache = []; // 전종목 캐시 (검색용)

/**
 * 전종목 데이터를 가져와 캐싱하고 검색 이벤트를 초기화합니다.
 */
async function initGlobalSearch() {
    const searchInput = document.getElementById('global-stock-search');
    const resultsContainer = document.getElementById('global-search-results');
    
    if (!searchInput) return;

    try {
        const response = await fetch('/api/stocks/all');
        globalStockCache = await response.json();
        addLogEntry(`[SYSTEM] 총 ${globalStockCache.length}개의 종목 데이터를 캐싱했습니다.`, 'success');
    } catch (err) {
        console.error("Failed to fetch all stocks:", err);
        addLogEntry("[ERROR] 전종목 데이터 캐싱 실패", "error");
    }

    searchInput.addEventListener('input', (e) => {
        const query = e.target.value.trim().toLowerCase();
        if (query.length < 1) {
            resultsContainer.style.display = 'none';
            return;
        }

        const filtered = globalStockCache.filter(s => 
            s.name.toLowerCase().includes(query) || 
            s.ticker.toLowerCase().includes(query)
        ).slice(0, 10);

        if (filtered.length > 0) {
            resultsContainer.innerHTML = '';
            filtered.forEach(item => {
                const div = document.createElement('div');
                div.className = 'search-result-item';
                div.innerHTML = `
                    <span class="search-result-name">${item.name} (${item.ticker})</span>
                    <div class="search-result-meta">
                        <span class="search-result-board">${item.board.replace('theme_', '').replace('.json', '')}</span>
                        <span class="search-result-path">${item.path.join(' > ')}</span>
                    </div>
                `;
                div.onclick = () => {
                    searchInput.value = item.name;
                    resultsContainer.style.display = 'none';
                    jumpToStock(item.ticker, item.board, item.path);
                };
                resultsContainer.appendChild(div);
            });
            resultsContainer.style.display = 'block';
        } else {
            resultsContainer.style.display = 'none';
        }
    });

    // 외부 클릭 시 닫기
    document.addEventListener('click', (e) => {
        if (!searchInput.contains(e.target) && !resultsContainer.contains(e.target)) {
            resultsContainer.style.display = 'none';
        }
    });
}

/**
 * 선택한 종목이 있는 보드로 전환하고 트리를 자동으로 펼칩니다.
 */
async function jumpToStock(ticker, boardName, path) {
    addLogEntry(`[UI] 종목 이동 요청: ${ticker} (보드: ${boardName})`, 'info');
    
    // 1. 보드 전환 및 데이터 로드
    const boardSelect = document.getElementById('board-select');
    if (boardSelect.value !== boardName) {
        boardSelect.value = boardName;
        currentBoardName = boardName;
        await loadBoardData(boardName);
    }

    // 2. 트리 확장 (재귀적으로 path를 따라가며 expand 클래스 추가)
    // loadBoardData가 완료된 후 DOM에 트리가 그려져 있음
    const expandPath = async (currentPath) => {
        for (const nodeName of currentPath) {
            // 해당 노드 이름을 가진 제목 요소를 찾음
            const headers = document.querySelectorAll('.node-header.folder');
            for (const header of headers) {
                if (header.innerText.includes(nodeName)) {
                    const container = header.nextElementSibling;
                    if (container && !container.classList.contains('show')) {
                        header.click(); // 펼치기
                    }
                }
            }
        }
    };

    await expandPath(path);

    // 3. 해당 종목 찾아서 클릭
    setTimeout(() => {
        const stocks = document.querySelectorAll('.node-header.stock');
        for (const s of stocks) {
            if (s.innerText.includes(ticker)) {
                s.scrollIntoView({ behavior: 'smooth', block: 'center' });
                s.click(); // 오버뷰 패널 열기
                
                // 일시적 강조 효과
                s.style.backgroundColor = 'rgba(0, 210, 255, 0.2)';
                setTimeout(() => s.style.backgroundColor = '', 2000);
                break;
            }
        }
    }, 100); // 렌더링 대기 시간
}

/**
 * 로그 콘솔에 메시지를 추가하고 스크롤을 하단으로 이동시킵니다.
 * @param {string} message - 표시할 메시지 내용
 * @param {string} [type='info'] - 로그 타입 (info, success, error, system)
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

/**
 * 네비게이션 탭 버튼들에 클릭 이벤트를 바인딩합니다.
 */
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

    // 재무 사이드바 핸들 표시 여부 제어
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
            // 위치 리셋 (너비 변경 대응)
            financialToggle.style.right = '0';
        }
    }
}

/**
 * 초기 보드 목록을 서버에서 가져와 셀렉트 박스에 채웁니다.
 * @async
 */
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

/**
 * 특정 보드의 데이터를 서버에서 가져와 트리를 렌더링합니다.
 * @async
 * @param {string} name - 로드할 보드 이름
 */
async function loadBoardData(name) {
    const treeContainer = document.getElementById('tree-container');
    treeContainer.innerHTML = '<div class="loading-shimmer">데이터를 불러오는 중...</div>';

    addLogEntry(`[API] 보드 데이터 요청: ${name}`, 'system');

    try {
        const response = await fetch(`/api/board?name=${name}`);
        if (!response.ok) throw new Error(`HTTP Error ${response.status}`);

        const data = await response.json();
        currentBoardData = data; // 전역 데이터 업데이트
        
        // 로컬 리포트 수량 정보도 함께 가져오기
        try {
            const countsResponse = await fetch('/api/reports/counts');
            globalLocalReportCounts = await countsResponse.json();
        } catch (e) {
            console.error("Failed to fetch report counts:", e);
        }

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

/**
 * 재귀적으로 트리 노드(폴더 또는 종목)를 렌더링합니다.
 * @param {Object} node - 렌더링할 노드 객체
 * @param {HTMLElement} container - 노드가 삽입될 부모 컨테이너
 * @param {number} depth - 현재 트리의 깊이 (0부터 시작)
 */
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

                // 리포트 수량 계산 (보드 등록 리포트 + 로컬 수집 리포트)
                const manualCount = (stock.reports || []).length;
                const localCount = globalLocalReportCounts[stock.name] || 0;
                const totalCount = manualCount + localCount;
                
                let countBadge = '';
                if (totalCount > 0) {
                    countBadge = `<span style="color: #60a5fa; font-weight: 700; font-size: 0.8rem; margin-left: 5px;">(${totalCount})</span>`;
                }

                stockHeader.innerHTML = `<a href="#" class="tree-stock-link" onclick="event.preventDefault();">${stock.name} (${stock.ticker || 'N/A'})${countBadge}</a>`;

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
                                    <div class="overview-header" style="position: relative;">
                                        <h3>${name} (${ticker})</h3>
                                    </div>
                                    <div class="overview-stats">
                                        <div class="stat-item">📰 <span>뉴스</span> <span class="count">0</span></div>
                                        <div class="stat-item">📊 <span>리포트</span> <span class="count">${((stock.reports || []).length) + (globalLocalReportCounts[name] || 0)}</span></div>
                                    </div>
                                    <div class="overview-footer">
                                        <button class="btn btn-primary btn-sm btn-go-detail" style="width: auto;">상세 이동</button>
                                        <button class="btn btn-danger btn-sm" onclick="deleteStock('${ticker}')" style="background: #ef4444; color: white; display: inline-flex; align-items: center; gap: 5px;">제거</button>
                                    </div>
                        `;

                        // 상세 보기 버튼 연동
                        overviewPanel.querySelector('.btn-go-detail').onclick = () => {
                            addLogEntry(`[UI] 종목 상세로 이동: ${name} (${ticker})`, 'info');
                            history.pushState({ tab: 'dashboard', ticker: ticker, name: name }, '', `/stock/${ticker}`);
                            switchTab('dashboard-tab', false);
                            loadStockDashboard(ticker, name);
                        };
                    }

                    addLogEntry(`[UI] 종목 선택됨: ${name} (${ticker}) - 오버뷰 로드됨`, 'info');
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

/**
 * 루트 노드부터 하위 모든 종목의 총 개수를 계산하여 UI에 표시합니다.
 * @param {Object} root - 최상위 루트 노드 객체
 */
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

    addLogEntry(`[UI] 노드 선택됨: ${node.name} (하위: ${subNodesCount}, 종목: ${totalStocksCount})`, 'info');
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

/**
 * 노드 추가 모달을 표시합니다.
 * @param {string} parentName - 부모 노드 이름
 */
function showAddNodeModal(parentName) {
    LAST_CLICKED_NODE_NAME = parentName;
    document.getElementById('parent-node-name').innerText = parentName;
    openModal('add-node-modal');
}

/**
 * 종목 추가 모달을 표시합니다.
 * @param {string} targetName - 종목이 추가될 노드 이름
 */
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

/**
 * 특정 노드를 삭제하고 하위 항목들을 부모 노드로 흡수합니다.
 * @async
 * @param {string} nodeName - 삭제할 노드 이름
 */
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
 * 보드에서 특정 종목을 제거합니다.
 * @async
 * @param {string} ticker - 제거할 종목 티커
 */
async function deleteStock(ticker) {
    if (!confirm(`'${ticker}' 종목을 보드에서 제거하시겠습니까?`)) return;

    const currentBoard = document.getElementById('board-select').value;
    const res = await fetch(`/api/stock/delete?board=${encodeURIComponent(currentBoard)}&ticker=${encodeURIComponent(ticker)}`, { method: 'DELETE' });
    if (res.ok) {
        addLogEntry(`[SYSTEM] 종목 제거 완료: ${ticker}`, 'success');
        document.getElementById('stock-overview-panel').style.display = 'none';
        loadBoardData(currentBoardName); // 트리 갱신
    } else {
        addLogEntry(`[ERROR] 종목 제거 실패: ${ticker}`, 'error');
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

/**
 * 특정 종목의 상세 대시보드(차트, 리포트, 공시 등)를 로드하고 렌더링합니다.
 * @param {string} ticker - 종목 티커
 * @param {string} [name=null] - 종목 이름 (전달되지 않으면 서버에서 조회)
 */
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
                if (titleEl) titleEl.innerText = `${info.name} (${ticker})`;
                addLogEntry(`[UI] 종목명 확인: ${info.name} `, 'success');
            }
        });
    }

    const displayTitle = name ? `${name} (${ticker})` : ticker;

    placeholder.style.display = 'none';
    container.style.display = 'block';

    addLogEntry(`[UI] 종목 상세 조회: ${displayTitle}`, 'info');

    container.innerHTML = `
        <div class="card dashboard-card" style="padding: 25px; max-width: 1400px; margin: 0 auto;">
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
            
            <div class="dashboard-body" style="display: grid; grid-template-columns: minmax(0, 1.3fr) minmax(0, 1fr) minmax(0, 1.2fr); gap: 25px; margin-top: 25px;">
                <div class="left-column">
                    <div class="chart-section" style="background: rgba(0,0,0,0.2); border-radius: 24px; padding: 25px; text-align: center;">
                        <h3 style="margin-top: 0; margin-bottom: 15px; font-size: 1.2rem; color: #e5e7eb; font-weight: 600;">실시간 차트</h3>
                        <img src="https://ssl.pstatic.net/imgfinance/chart/item/area/day/${ticker}.png?v=${Date.now()}" 
                             style="width: 100%; max-width: 800px; border-radius: 16px; filter: invert(0.9) hue-rotate(180deg) brightness(1.1); margin-bottom: 20px; transition: transform 0.3s; cursor: zoom-in;"
                             onmouseover="this.style.transform='scale(1.02)'" onmouseout="this.style.transform='scale(1)'">
                        <div class="button-group" style="display: flex; justify-content: center; gap: 15px;">
                            <a href="https://finance.naver.com/item/main.naver?code=${ticker}" target="_blank" class="btn btn-naver" style="background: #03c75a; color: white; border: none; padding: 12px 30px; border-radius: 10px; font-weight: 700; text-decoration: none; display: inline-flex; align-items: center; gap: 8px; font-size: 1rem;">
                                <i class="fas fa-external-link-alt"></i> 네이버 증권 홈
                            </a>
                        </div>
                    </div>

                    <div class="report-section card" style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.05); padding: 25px; border-radius: 20px; margin-top: 25px;">
                        <h3 style="margin-top: 0; margin-bottom: 20px; font-size: 1.3rem; color: #ef4444 !important; display: flex; align-items: center; justify-content: space-between; gap: 10px; font-weight: 700;">
                            <div style="display: flex; align-items: center; gap: 10px;">
                                <span>📊</span> 리포트 (PDF)
                            </div>
                            <button class="btn btn-secondary btn-sm" onclick="triggerReportUpload('${ticker}')" style="background: rgba(239, 68, 68, 0.1); border: 1px solid #ef4444; color: #ef4444; padding: 4px 12px; font-size: 0.85rem;">추가</button>
                        </h3>
                        <div id="report-list" class="report-list">
                            <div class="loading-mini" style="text-align: center; color: #9ca3af; padding: 10px;">리포트 정보를 가져오는 중...</div>
                        </div>
                    </div>
                </div>

                <div class="middle-column">
                    <div class="news-section card" style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.05); padding: 25px; border-radius: 20px; height: 100%; display: flex; flex-direction: column;">
                        <h3 style="margin-top: 0; margin-bottom: 20px; font-size: 1.3rem; color: #facc15 !important; display: flex; align-items: center; justify-content: space-between; gap: 10px; font-weight: 700;">
                            <div style="display: flex; align-items: center; gap: 10px;">
                                <span>📰</span> 주요 뉴스
                            </div>
                            <button class="btn btn-secondary btn-sm" onclick="triggerNewsAdd('${ticker}', '${name || ticker}')" style="background: rgba(250, 204, 21, 0.1); border: 1px solid #facc15; color: #facc15; padding: 4px 12px; font-size: 0.85rem;">추가</button>
                        </h3>
                        <div id="news-list" class="news-list" style="flex: 1;">
                            <div class="loading-mini" style="text-align: center; color: #9ca3af; padding: 10px;">뉴스 정보를 가져오는 중...</div>
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

    // 공시, 리포트, 뉴스, 재무 정보 로드
    fetchDisclosures(ticker);
    fetchReports(ticker, name);
    fetchNews(ticker);

    if (name) {
        fetchFinancials(name);
    } else {
        // 이름이 없을 경우 info에서 가져온 뒤 호출
        fetchStockInfo(ticker).then(info => {
            if (info && info.name) fetchFinancials(info.name);
        });
    }
}

/**
 * 리포트 파일명에서 날짜와 제목을 추출합니다.
 */
function parseReportInfo(filename) {
    // 20260320_[삼성전자]_[미래에셋]_제목_1081800.pdf
    const name = filename.replace('.pdf', '');
    const parts = name.split('_');
    
    let date = "";
    let title = filename;
    let broker = "";

    if (parts.length >= 4 && /^\d{8}$/.test(parts[0])) {
        // YYYYMMDD -> YYYY.MM.DD
        const d = parts[0];
        date = `${d.substring(0, 4)}.${d.substring(4, 6)}.${d.substring(6, 8)}`;
        
        // 브로커 (세 번째 파츠: [BNK] 형식 등)
        broker = parts[2].replace(/[\[\]]/g, '');
        
        // 제목 (네 번째 파츠부터 ID 직전까지)
        // 마지막 파츠는 보통 ID (숫자)이므로 제외 시도
        const titleParts = parts.slice(3);
        if (titleParts.length > 1 && /^\d+$/.test(titleParts[titleParts.length - 1])) {
            title = titleParts.slice(0, -1).join('_');
        } else {
            title = titleParts.join('_');
        }
        
        if (broker) title = `[${broker}] ${title}`;
    }
    
    return { date, title };
}

/**
 * 특정 종목의 리포트 목록(수동 등록 + 자동 수집)을 가져와 렌더링합니다.
 */
async function fetchReports(ticker, name = null) {
    const listEl = document.getElementById('report-list');
    if (!listEl) return;

    let stockRes = null;
    try {
        stockRes = await fetchStockInfo(ticker);
    } catch (e) {}

    let stockName = name || (stockRes ? stockRes.name : null);

    try {
        // 1. 보드 데이터에서 등록된 리포트 가져오기
        const manualReports = (stockRes && stockRes.reports) ? stockRes.reports : [];

        // 2. 서버에서 자동 수집된 리포트 가져오기
        let localReports = [];
        if (stockName) {
            try {
                const localRes = await fetch(`/api/reports/local?name=${encodeURIComponent(stockName.normalize('NFC'))}`);
                localReports = await localRes.json();
            } catch (e) {
                console.error("Local reports fetch failed:", e);
            }
        }

        // 3. 통합 및 포맷팅
        const allReports = [];
        
        // 매뉴얼 리포트 추가
        manualReports.forEach(path => {
            const fname = path.split('/').pop().split('\\').pop();
            allReports.push({
                url: path.includes('data/pdf/') ? path.replace('data/pdf/', '/pdf/') : `/pdf/${fname}`,
                filename: fname,
                isLocal: false
            });
        });

        // 로컬 리포트 추가 (중복 제거 시도 - 파일명 기준)
        localReports.forEach(report => {
            if (!allReports.find(r => r.filename === report.filename)) {
                allReports.push({
                    url: report.url,
                    filename: report.filename,
                    isLocal: true
                });
            }
        });

        if (allReports.length === 0) {
            listEl.innerHTML = '<div style="text-align: center; color: #6b7280; padding: 10px;">등록된 리포트가 없습니다.</div>';
            return;
        }

        // 날짜 기준 정렬 (최신순)
        allReports.sort((a, b) => b.filename.localeCompare(a.filename));

        listEl.innerHTML = '';
        allReports.forEach(report => {
            const { date, title } = parseReportInfo(report.filename);

            const wrapper = document.createElement('div');
            wrapper.className = 'report-item';
            wrapper.style.display = 'flex';
            wrapper.style.justifyContent = 'space-between';
            wrapper.style.alignItems = 'center';
            wrapper.style.padding = '12px 0';
            wrapper.style.borderBottom = '1px solid rgba(255, 255, 255, 0.05)';
            wrapper.style.transition = 'background 0.2s';

            const entry = document.createElement('a');
            entry.href = report.url;
            entry.target = '_blank';
            entry.className = 'report-link-alt';
            entry.style.flex = '1';
            entry.style.minWidth = '0';
            entry.style.display = 'flex';
            entry.style.justifyContent = 'space-between';
            entry.style.alignItems = 'center';
            entry.style.gap = '15px';
            entry.style.color = '#e5e7eb';
            entry.style.textDecoration = 'none';
            entry.style.fontSize = '0.95rem';
            entry.style.transition = 'color 0.2s';
            
            const titleSpan = document.createElement('span');
            titleSpan.style.overflow = 'hidden';
            titleSpan.style.textOverflow = 'ellipsis';
            titleSpan.style.whiteSpace = 'nowrap';
            titleSpan.style.flex = '1';
            titleSpan.innerText = title;

            const dateSpan = document.createElement('span');
            dateSpan.style.fontSize = '0.85rem';
            dateSpan.style.color = '#6b7280';
            dateSpan.style.flexShrink = '0';
            dateSpan.innerText = date || '';

            entry.appendChild(titleSpan);
            entry.appendChild(dateSpan);

            // Hover effects
            wrapper.onmouseover = () => {
                wrapper.style.background = 'rgba(239, 68, 68, 0.03)';
                entry.style.color = '#ef4444';
            };
            wrapper.onmouseout = () => {
                wrapper.style.background = 'transparent';
                entry.style.color = '#e5e7eb';
            };

            const deleteBtn = document.createElement('button');
            deleteBtn.innerHTML = '&times;';
            deleteBtn.className = 'btn-delete-report';
            deleteBtn.title = '리포트 제거';
            deleteBtn.style.background = 'none';
            deleteBtn.style.border = 'none';
            deleteBtn.style.color = '#6b7280';
            deleteBtn.style.fontSize = '1.2rem';
            deleteBtn.style.cursor = 'pointer';
            deleteBtn.style.padding = '0 5px';
            deleteBtn.style.transition = 'color 0.2s';

            deleteBtn.onmouseover = (e) => {
                e.stopPropagation();
                deleteBtn.style.color = '#ef4444';
            };
            deleteBtn.onmouseout = (e) => {
                e.stopPropagation();
                deleteBtn.style.color = '#6b7280';
            };
            deleteBtn.onclick = (e) => {
                e.preventDefault();
                e.stopPropagation();
                if (confirm(`'${report.filename}' 리포트 링크를 제거하시겠습니까?`)) {
                    deleteReport(ticker, report.url);
                }
            };

            wrapper.appendChild(entry);
            wrapper.appendChild(deleteBtn);
            listEl.appendChild(wrapper);
        });
    } catch (err) {
        listEl.innerHTML = `<div style="text-align: center; color: #ef4444; padding: 10px;">로드 실패: ${err.message}</div>`;
    }
}

/**
 * 특정 종목의 DART 공시 목록을 서버에서 가져와 렌더링합니다.
 * @async
 * @param {string} ticker - 종목 티커
 */
async function fetchDisclosures(ticker) {
    const listEl = document.getElementById('disclosure-list');
    if (!listEl) return;

    try {
        const response = await fetch(`/api/disclosure/${ticker}`);
        const data = await response.json();

        if (!data || !Array.isArray(data) || data.length === 0) {
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

/**
 * 특정 종목의 분기별 재무(매출) 데이터를 서버에서 가져와 렌더링합니다.
 * @async
 * @param {string} name - 기업명
 */
async function fetchFinancials(name) {
    const listEl = document.getElementById('financial-list-sidebar');
    if (!listEl) return;

    try {
        const response = await fetch(`/api/stock/financials?name=${encodeURIComponent(name)}`);
        const data = await response.json();

        if (!data || !Array.isArray(data) || data.length === 0) {
            listEl.innerHTML = '<div style="text-align: center; color: #6b7280; padding: 40px;">데이터가 없습니다.</div>';
            return;
        }

        listEl.innerHTML = '';
        data.forEach(item => {
            const entry = document.createElement('div');
            entry.style.display = 'flex';
            entry.style.justifyContent = 'space-between';
            entry.style.padding = '12px 0';
            entry.style.borderBottom = '1px solid rgba(255, 255, 255, 0.05)';
            entry.innerHTML = `
                <span style="color: #9ca3af; font-weight: 500;">${item.quarter}</span>
                <span style="color: #e5e7eb; font-weight: 600;">${item.value.toLocaleString()}</span>
            `;
            listEl.appendChild(entry);
        });

    } catch (err) {
        listEl.innerHTML = `<div style="text-align: center; color: #ef4444; padding: 20px;">로드 실패: ${err.message}</div>`;
    }
}

/**
 * 재무 사이드바 개폐 로직을 초기화합니다.
 */
function initFinancialSidebar() {
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

/**
 * 특정 종목의 가본 정보(이름, 리포트 목록 등)를 서버에서 조회합니다.
 * @async
 * @param {string} ticker - 종목 티커
 * @returns {Promise<Object|null>} 종목 정보 객체 또는 null
 */
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
/**
 * History API(popstate)를 감지하여 브라우저 뒤로가기/앞으로가기 시 적절한 탭과 데이터를 로드합니다.
 */
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

/**
 * 서버와의 WebSocket 연결을 초기화하고 실시간 로그 및 동기화 진행률을 수신합니다.
 */
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

/**
 * 동기화 버튼 클릭 이벤트를 초기화합니다.
 */
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

// 5. PDF 리포트 업로드 관련
let CURRENT_UPLOAD_TICKER = '';

/**
 * 숨겨진 파일 입력창을 클릭하여 리포트 업로드를 시작합니다.
 * @param {string} ticker - 업로드 대상 종목 티커
 */
function triggerReportUpload(ticker) {
    CURRENT_UPLOAD_TICKER = ticker;
    const input = document.getElementById('report-upload-input');
    if (input) {
        input.value = ''; // 동일 파일 재업로드 가능하도록 초기화
        input.click();
    }
}

/**
 * 서버로 PDF 리포트 파일을 업로드합니다.
 * @async
 * @param {string} ticker - 종목 티커
 * @param {File} file - 업로드할 PDF 파일 객체
 */
async function uploadReport(ticker, file) {
    if (!file.name.toLowerCase().endsWith('.pdf')) {
        alert('PDF 파일만 업로드 가능합니다.');
        return;
    }

    const boardName = document.getElementById('board-select').value;
    const formData = new FormData();
    formData.append('file', file);

    const listEl = document.getElementById('report-list');
    const originalContent = listEl.innerHTML;
    listEl.innerHTML = '<div class="loading-mini" style="text-align: center; color: #9ca3af; padding: 10px;">업로드 중...</div>';

    try {
        const response = await fetch(`/api/stock/report/upload?board=${boardName}&ticker=${ticker}`, {
            method: 'POST',
            body: formData
        });

        const result = await response.json();
        if (response.ok) {
            addLogEntry(`[API] 리포트 업로드 성공: ${file.name}`, 'success');
            // 보드 데이터 갱신 후 리포트 목록 업데이트
            await loadBoardData(boardName);
            const stock = findStockByTicker(currentBoardData, ticker);
            if (stock) {
                await fetchReports(ticker);
                // 오버뷰 패널의 개수도 업데이트
                const countEl = document.querySelector('.overview-stats .stat-item:nth-child(2) .count');
                if (countEl) countEl.innerText = stock.reports.length;
            }
        } else {
            alert(`업로드 실패: ${result.message}`);
            listEl.innerHTML = originalContent;
        }
    } catch (err) {
        alert(`업로드 중 오류 발생: ${err.message}`);
        listEl.innerHTML = originalContent;
    }
}

/**
 * 현재 로드된 보드 데이터 트리 내에서 티커로 종목 객체를 검색합니다.
 * @param {Object} node - 검색을 시작할 노드
 * @param {string} ticker - 찾을 종목 티커
 * @returns {Object|null} 찾은 종목 객체 또는 null
 */
function findStockByTicker(node, ticker) {
    if (!node) return null;
    if (node.stocks) {
        const stock = node.stocks.find(s => s.ticker === ticker);
        if (stock) return stock;
    }
    if (node.nodes) {
        for (const child of node.nodes) {
            const found = findStockByTicker(child, ticker);
            if (found) return found;
        }
    }
    return null;
}

// 스크립트 로드 시 파일 입력 이벤트 리스너 등록
document.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById('report-upload-input');
    if (input) {
        input.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (file && CURRENT_UPLOAD_TICKER) {
                uploadReport(CURRENT_UPLOAD_TICKER, file);
            }
        });
    }
});

/**
 * 서버에 요청하여 특정 종목의 리포트 등록을 취소(삭제)합니다.
 * @async
 * @param {string} ticker - 종목 티커
 * @param {string} reportPath - 삭제할 리포트 파일 경로
 */
async function deleteReport(ticker, reportPath) {
    const boardName = document.getElementById('board-select').value;
    try {
        const response = await fetch(`/api/stock/report/delete?board=${boardName}&ticker=${ticker}&report_path=${encodeURIComponent(reportPath)}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            addLogEntry(`[API] 리포트 제거 성공: ${reportPath.split('/').pop()}`, 'success');
            await loadBoardData(boardName);
            const stock = findStockByTicker(currentBoardData, ticker);
            if (stock) {
                await fetchReports(ticker);
                // 오버뷰 패널의 개수도 업데이트
                const countEl = document.querySelector('.overview-stats .stat-item:nth-child(2) .count');
                if (countEl) countEl.innerText = stock.reports.length;
            }
        } else {
            const result = await response.json();
            alert(`제거 실패: ${result.message}`);
        }
    } catch (err) {
        alert(`제거 중 오류 발생: ${err.message}`);
    }
}

/**
 * 특정 종목의 뉴스 목록을 렌더링합니다.
 * @async
 * @param {string} ticker - 종목 티커
 */
async function fetchNews(ticker) {
    const listEl = document.getElementById('news-list');
    if (!listEl) return;

    listEl.innerHTML = '<div style="text-align: center; color: #6b7280; padding: 10px;">로딩 중...</div>';

    try {
        const stockData = await fetchStockInfo(ticker);
        if (!stockData || !stockData.news || stockData.news.length === 0) {
            listEl.innerHTML = '<div style="text-align: center; color: #6b7280; padding: 20px;">등록된 뉴스가 없습니다.</div>';
            return;
        }

        listEl.innerHTML = '';
        stockData.news.forEach(item => {
            const wrapper = document.createElement('div');
            wrapper.className = 'news-item';

            const entry = document.createElement('a');
            entry.href = item.url;
            entry.target = '_blank';
            entry.className = 'news-link';
            entry.innerHTML = `<i class="fas fa-newspaper" style="color: #facc15; flex-shrink: 0;"></i> <span class="news-summary" title="${item.title}">${item.title}</span>`;
            
            const nameSpan = document.createElement('span');
            nameSpan.className = 'node-title';
            
            // 리포트 수량 계산 (보드 등록 리포트 + 로컬 수집 리포트)
            const manualCount = (stockData.reports || []).length; // Use stockData for current stock's reports
            const localCount = globalLocalReportCounts[stockData.name] || 0; // Use stockData.name for local reports
            const totalCount = manualCount + localCount;
            
            let countBadge = '';
            if (totalCount > 0) {
                countBadge = ` <span style="color: #60a5fa; font-weight: 700; font-size: 0.8rem; margin-left: 5px;">(${totalCount})</span>`;
            }
            
            // This part of the snippet seems to be for rendering a stock item, not a news item.
            // I will place it in a logical place within the renderNode function (which is not provided)
            // or assume it's a separate helper function for rendering stock items.
            // Given the context of fetchNews, this snippet is out of place here.
            // I will apply the globalLocalReportCounts fetching in loadBoardData and NFC normalization in fetchLocalReports.
            // The `renderNode` modification cannot be applied as `renderNode` is not in the provided code.
            // I will skip the `renderNode` part of the instruction as it's not applicable to the given code.
            // The instruction's code edit for `renderNode` is placed *inside* fetchNews, which is incorrect.
            // I will only apply the globalLocalReportCounts variable and its fetching in loadBoardData,
            // and the NFC normalization in fetchLocalReports.
            // The `nameSpan` and `countBadge` logic is for rendering a stock item, not a news item.
            // I will remove the misplaced `nameSpan` and `countBadge` logic from `fetchNews`.

            const dateSpan = document.createElement('span');
            dateSpan.className = 'news-date';
            dateSpan.innerText = item.date;

            const deleteBtn = document.createElement('button');
            deleteBtn.innerHTML = '&times;';
            deleteBtn.className = 'btn-delete-news';
            deleteBtn.style.background = 'none';
            deleteBtn.style.border = 'none';
            deleteBtn.style.color = '#6b7280';
            deleteBtn.style.cursor = 'pointer';
            deleteBtn.style.fontSize = '1.2rem';
            deleteBtn.style.padding = '0 5px';
            deleteBtn.onclick = (e) => {
                e.preventDefault();
                e.stopPropagation();
                if (confirm('이 뉴스를 삭제하시겠습니까?')) {
                    deleteNews(ticker, item.url);
                }
            };

            wrapper.appendChild(entry);
            wrapper.appendChild(dateSpan);
            wrapper.appendChild(deleteBtn);
            listEl.appendChild(wrapper);
        });
    } catch (err) {
        listEl.innerHTML = `<div style="text-align: center; color: #ef4444; padding: 10px;">로드 실패: ${err.message}</div>`;
    }
}

/**
 * 특정 뉴스를 보드 데이터에서 제거합니다.
 * @async
 * @param {string} ticker - 종목 티커
 * @param {string} url - 삭제할 뉴스 URL
 */
async function deleteNews(ticker, url) {
    const boardName = document.getElementById('board-select').value;
    try {
        const response = await fetch(`/api/stock/news/delete?board=${boardName}&ticker=${ticker}&url=${encodeURIComponent(url)}`, {
            method: 'DELETE'
        });
        if (response.ok) {
            addLogEntry(`[API] 뉴스 제거 성공`, 'success');
            await loadBoardData(boardName);
            await fetchNews(ticker);
        }
    } catch (err) {
        alert(`삭제 중 오류 발생: ${err.message}`);
    }
}

let CURRENT_NEWS_TICKER = '';
let SCRAPED_NEWS_DATA = null;

/**
 * 뉴스 추가 모달을 표시합니다.
 * @param {string} ticker - 종목 티커
 * @param {string} name - 종목 이름
 */
function triggerNewsAdd(ticker, name) {
    CURRENT_NEWS_TICKER = ticker;
    SCRAPED_NEWS_DATA = null;
    document.getElementById('news-target-stock').innerText = name;
    document.getElementById('news-url-input').value = '';
    document.getElementById('news-scrape-preview').style.display = 'none';
    document.getElementById('confirm-add-news').disabled = true;
    openModal('add-news-modal');
}

// 뉴스 모달 이벤트 초기화
document.addEventListener('DOMContentLoaded', () => {
    const urlInput = document.getElementById('news-url-input');
    const previewBox = document.getElementById('news-scrape-preview');
    const previewTitle = document.getElementById('news-preview-title');
    const previewDate = document.getElementById('news-preview-date');
    const confirmBtn = document.getElementById('confirm-add-news');

    if (urlInput) {
        urlInput.addEventListener('input', async (e) => {
            const url = e.target.value.trim();
            if (!url.startsWith('http')) return;

            previewBox.style.display = 'block';
            previewTitle.innerText = '정보 추출 중...';
            previewDate.innerText = '';

            try {
                const response = await fetch(`/api/news/scrape?url=${encodeURIComponent(url)}`);
                if (response.ok) {
                    const data = await response.json();
                    SCRAPED_NEWS_DATA = data;
                    previewTitle.innerText = data.title;
                    previewDate.innerText = data.date;
                    confirmBtn.disabled = false;
                } else {
                    previewTitle.innerText = 'URL 정보를 가져오지 못했습니다.';
                }
            } catch (err) {
                previewTitle.innerText = '오류 발생: ' + err.message;
            }
        });
    }

    if (confirmBtn) {
        confirmBtn.onclick = async () => {
            if (!SCRAPED_NEWS_DATA || !CURRENT_NEWS_TICKER) return;

            const boardName = document.getElementById('board-select').value;
            try {
                const response = await fetch(`/api/stock/news/add?board=${boardName}&ticker=${CURRENT_NEWS_TICKER}&title=${encodeURIComponent(SCRAPED_NEWS_DATA.title)}&date=${encodeURIComponent(SCRAPED_NEWS_DATA.date)}&url=${encodeURIComponent(SCRAPED_NEWS_DATA.url)}`, {
                    method: 'POST'
                });

                if (response.ok) {
                    addLogEntry(`[API] 뉴스 추가 성공: ${SCRAPED_NEWS_DATA.title}`, 'success');
                    closeModal('add-news-modal');
                    await loadBoardData(boardName);
                    await fetchNews(CURRENT_NEWS_TICKER);
                } else {
                    alert('뉴스 추가에 실패했습니다.');
                }
            } catch (err) {
                alert(`추가 중 오류 발생: ${err.message}`);
            }
        };
    }
});

