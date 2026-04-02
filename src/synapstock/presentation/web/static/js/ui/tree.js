/**
 * @fileoverview 마인드맵 트리 렌더링 및 보드 관련 UI 모듈.
 * @module ui/tree
 */
import { addLogEntry, switchTab } from './tabs.js';

/**
 * @typedef {Object} StockNode
 * @property {string} name - 종목명.
 * @property {string} ticker - 종목 티커 심볼.
 * @property {string[]} reports - 등록된 리포트 경로 배열.
 */

/**
 * @typedef {Object} TreeNode
 * @property {string} name - 노드 이름.
 * @property {TreeNode[]} nodes - 하위 노드 배열.
 * @property {StockNode[]} stocks - 이 노드에 직접 속한 종목 배열.
 */

/**
 * 노드와 그 자손에 속한 종목의 총 개수를 재귀적으로 계산합니다.
 *
 * @param {TreeNode} node - 계산을 시작할 노드.
 * @returns {number} 해당 노드 하위의 총 종목 수.
 */
export function countRecursiveStocks(node) {
    let count = (node.stocks || []).length;
    if (node.nodes) {
        node.nodes.forEach(child => { count += countRecursiveStocks(child); });
    }
    return count;
}

/**
 * 보드 트리를 재귀적으로 탐색하여 티커가 일치하는 종목 객체를 반환합니다.
 *
 * @param {TreeNode|null} node - 탐색을 시작할 노드.
 * @param {string} ticker - 찾을 종목의 티커 심볼.
 * @returns {StockNode|null} 찾은 종목 객체. 없으면 `null`.
 */
export function findStockByTicker(node, ticker) {
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

/**
 * 루트 노드 기준 하위 전체 종목 수를 계산하여 `#total-stocks-count` 요소에 표시합니다.
 *
 * @param {TreeNode} root - 루트 노드.
 * @returns {void}
 */
export function updateStockCount(root) {
    const count = countRecursiveStocks(root);
    const countEl = document.getElementById('total-stocks-count');
    if (countEl) countEl.innerText = count;
}

/**
 * 선택된 폴더 노드의 정보를 우측 오버뷰 패널(`#stock-overview-panel`)에 렌더링합니다.
 *
 * 루트 노드인 경우 삭제 버튼을 표시하지 않습니다.
 *
 * @param {TreeNode} node - 클릭된 노드 객체.
 * @param {TreeNode|null} currentBoardData - 현재 로드된 보드의 루트 노드. 루트 여부 판별에 사용.
 * @returns {void}
 */
export function updateNodeOverview(node, currentBoardData) {
    const overviewPanel = document.getElementById('stock-overview-panel');
    if (!overviewPanel) return;

    const subNodesCount = (node.nodes || []).length;
    const totalStocksCount = countRecursiveStocks(node);
    const isRoot = currentBoardData && currentBoardData.name === node.name;

    overviewPanel.style.display = 'block';
    overviewPanel.innerHTML = `
        <div class="overview-header">
            <h3 style="color:#facc15 !important;">📁 ${node.name}</h3>
        </div>
        <div class="overview-stats">
            <div class="stat-item">🌿 <span>하위 노드</span> <span class="count">${subNodesCount}</span></div>
            <div class="stat-item">🚀 <span>전체 종목</span> <span class="count">${totalStocksCount}</span></div>
        </div>
        <div class="overview-footer" style="display:flex;gap:10px;flex-wrap:wrap;">
            <button class="btn btn-secondary btn-sm" onclick="showAddNodeModal('${node.name}')">새 노드</button>
            <button class="btn btn-secondary btn-sm" onclick="showAddStockModal('${node.name}')">종목 추가</button>
            ${!isRoot ? `<button class="btn btn-danger btn-sm" onclick="deleteNode('${node.name}')" style="background:#ef4444;color:white;">제거</button>` : ''}
        </div>
    `;

    addLogEntry(`[UI] 노드 선택됨: ${node.name} (하위: ${subNodesCount}, 종목: ${totalStocksCount})`, 'info');
}

/**
 * 단일 트리 노드를 DOM에 재귀적으로 렌더링합니다.
 *
 * 모든 노드는 폴더로 취급되어 클릭 시 자식을 펼치거나 접을 수 있습니다.
 * depth가 1 미만인 경우 초기에 펼쳐진 상태로 렌더링됩니다.
 *
 * @param {TreeNode} node - 렌더링할 노드 객체.
 * @param {HTMLElement} container - 노드 엘리먼트를 삽입할 부모 DOM 컨테이너.
 * @param {number} depth - 현재 트리 깊이 (루트는 0).
 * @param {Object<string, number>} globalLocalReportCounts - 종목명 키의 로컬 리포트 수량 맵.
 * @param {TreeNode|null} currentBoardData - 현재 보드 루트 노드 (루트 판별용).
 * @param {function(string, string=): void} loadStockDashboard - 종목 대시보드 로드 함수.
 * @returns {void}
 */
export function renderNode(node, container, depth, globalLocalReportCounts, currentBoardData, loadStockDashboard) {
    const nodeEl = document.createElement('div');
    nodeEl.className = 'tree-node';

    const header = document.createElement('div');
    header.className = 'node-header folder';
    header.innerHTML = `<span class="node-title">${node.name}</span>`;

    const childrenContainer = document.createElement('div');
    childrenContainer.className = 'children-container';

    header.addEventListener('click', (e) => {
        e.stopPropagation();
        header.classList.toggle('expanded');
        childrenContainer.classList.toggle('show');
        updateNodeOverview(node, currentBoardData);
    });

    if (node.nodes) {
        node.nodes.forEach(child =>
            renderNode(child, childrenContainer, depth + 1, globalLocalReportCounts, currentBoardData, loadStockDashboard)
        );
    }

    if (node.stocks) {
        node.stocks.forEach(stock => {
            const stockHeader = document.createElement('div');
            stockHeader.className = 'node-header stock';
            stockHeader.style.cursor = 'pointer';

            const manualCount = (stock.reports || []).length;
            const localCount = globalLocalReportCounts[stock.name] || 0;
            const totalCount = manualCount + localCount;

            let countBadge = '';
            if (totalCount > 0) {
                countBadge = `<span style="color:#60a5fa;font-weight:700;font-size:0.8rem;margin-left:5px;">(${totalCount})</span>`;
            }

            stockHeader.innerHTML = `<a href="#" class="tree-stock-link" onclick="event.preventDefault();">${stock.name} (${stock.ticker || 'N/A'})${countBadge}</a>`;

            const handleStockClick = (e) => {
                e.preventDefault();
                e.stopPropagation();

                const { ticker, name } = stock;

                const overviewPanel = document.getElementById('stock-overview-panel');
                if (overviewPanel) {
                    overviewPanel.style.display = 'block';
                    overviewPanel.innerHTML = `
                        <div class="overview-header" style="position:relative;">
                            <h3>${name} (${ticker})</h3>
                        </div>
                        <div class="overview-stats">
                            <div class="stat-item">📰 <span>뉴스</span> <span class="count">${(stock.news || []).length}</span></div>
                            <div class="stat-item">📊 <span>리포트</span> <span class="count">${((stock.reports || []).length) + (globalLocalReportCounts[name] || 0)}</span></div>
                        </div>
                        <div class="overview-footer">
                            <button class="btn btn-primary btn-sm btn-go-detail" style="width:auto;">상세 이동</button>
                            <button class="btn btn-danger btn-sm" onclick="deleteStock('${ticker}')" style="background:#ef4444;color:white;display:inline-flex;align-items:center;gap:5px;">제거</button>
                        </div>
                    `;

                    overviewPanel.querySelector('.btn-go-detail').onclick = () => {
                        addLogEntry(`[UI] 종목 상세로 이동: ${name} (${ticker})`, 'info');
                        history.pushState({ tab: 'dashboard', ticker, name }, '', `/stock/${ticker}`);
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

    nodeEl.appendChild(header);
    nodeEl.appendChild(childrenContainer);
    container.appendChild(nodeEl);

    if (depth < 1) {
        header.classList.add('expanded');
        childrenContainer.classList.add('show');
    }
}

/**
 * 특정 종목을 찾아 해당 보드로 전환하고 트리 경로를 자동으로 펼칩니다.
 *
 * 다른 보드가 선택되어 있으면 먼저 보드를 전환한 뒤 경로를 따라 노드를 펼치고,
 * 해당 종목 항목으로 스크롤 이동합니다.
 *
 * @param {string} ticker - 이동할 종목의 티커 심볼.
 * @param {string} boardName - 종목이 속한 보드 파일명.
 * @param {string[]} path - 루트에서 종목까지의 노드 이름 배열.
 * @param {function(string): Promise<void>} loadBoardData - 보드 데이터 로드 함수.
 * @returns {Promise<void>}
 */
export async function jumpToStock(ticker, boardName, path, loadBoardData) {
    addLogEntry(`[UI] 종목 이동 요청: ${ticker} (보드: ${boardName})`, 'info');

    const boardSelect = document.getElementById('board-select');
    if (boardSelect.value !== boardName) {
        boardSelect.value = boardName;
        window._currentBoardName = boardName;
        await loadBoardData(boardName);
    }

    const expandPath = async (currentPath) => {
        for (const nodeName of currentPath) {
            const headers = document.querySelectorAll('.node-header.folder');
            for (const header of headers) {
                if (header.innerText.includes(nodeName)) {
                    const container = header.nextElementSibling;
                    if (container && !container.classList.contains('show')) {
                        header.click();
                    }
                }
            }
        }
    };

    await expandPath(path);

    setTimeout(() => {
        const stocks = document.querySelectorAll('.node-header.stock');
        for (const s of stocks) {
            if (s.innerText.includes(ticker)) {
                s.scrollIntoView({ behavior: 'smooth', block: 'center' });
                s.click();
                s.style.backgroundColor = 'rgba(0,210,255,0.2)';
                setTimeout(() => s.style.backgroundColor = '', 2000);
                break;
            }
        }
    }, 100);
}

/**
 * 서버에서 보드 목록을 조회하여 셀렉트 박스를 채우고, [불러오기] 버튼 이벤트를 등록합니다.
 *
 * @param {function(string): Promise<void>} loadBoardData - 선택된 보드의 데이터를 로드하는 함수.
 * @returns {Promise<void>}
 */
export async function initTree(loadBoardData) {
    const boardSelect = document.getElementById('board-select');
    const loadBtn = document.getElementById('load-board-btn');
    const treeContainer = document.getElementById('tree-container');

    treeContainer.innerHTML = '<div class="tree-empty-state">왼쪽 상단에서 보드를 선택하고 [불러오기]를 눌러주세요.</div>';
    addLogEntry('[API] 사용 가능한 보드 목록을 조회 중입니다...', 'system');

    try {
        const boardsRes = await fetch('/api/boards');
        const boards = await boardsRes.json();

        boardSelect.innerHTML = '<option value="" disabled selected>보드를 선택하세요</option>';
        boards.forEach(item => {
            const id = item.id || item;
            const name = item.name || item.replace('theme_', '');
            const option = document.createElement('option');
            option.value = id;
            option.textContent = name;
            boardSelect.appendChild(option);
        });

        addLogEntry(`[API] 총 ${boards.length}개의 마인드맵 보드를 찾았습니다.`, 'success');

        loadBtn.addEventListener('click', () => {
            const selectedName = boardSelect.value;
            if (!selectedName || selectedName === '') {
                addLogEntry('[WARN] 불러올 보드를 선택해 주세요.', 'error');
                return;
            }
            window._currentBoardName = selectedName;
            loadBoardData(selectedName);
        });
    } catch (err) {
        addLogEntry(`[ERROR] 보드 목록 조회 실패: ${err.message}`, 'error');
    }
}
