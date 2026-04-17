/**
 * @fileoverview 마인드맵 트리 렌더링 및 보드 이동 관련 모듈.
 * @module ui/mindmap/tree
 */
import { addLogEntry, switchTab } from '../tabs.js';

export function countRecursiveStocks(node) {
    let count = (node.stocks || []).length;
    if (node.nodes) {
        node.nodes.forEach(child => { count += countRecursiveStocks(child); });
    }
    return count;
}

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

export function updateStockCount(root) {
    const count = countRecursiveStocks(root);
    const countEl = document.getElementById('total-stocks-count');
    if (countEl) countEl.innerText = count;
}

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
    addLogEntry(`[UI] 노드 선택됨: ${node.name}`, 'info');
}

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
        node.nodes.forEach(child => renderNode(child, childrenContainer, depth + 1, globalLocalReportCounts, currentBoardData, loadStockDashboard));
    }

    if (node.stocks) {
        node.stocks.forEach(stock => {
            const stockHeader = document.createElement('div');
            stockHeader.className = 'node-header stock';
            stockHeader.style.cursor = 'pointer';
            const manualCount = (stock.reports || []).length;
            const localCount = globalLocalReportCounts[stock.name] || 0;
            const totalCount = manualCount + localCount;
            let countBadge = totalCount > 0 ? `<span style="color:#60a5fa;font-weight:700;font-size:0.8rem;margin-left:5px;">(${totalCount})</span>` : '';
            stockHeader.innerHTML = `<a href="#" class="tree-stock-link" onclick="event.preventDefault();">${stock.name} (${stock.ticker || 'N/A'})${countBadge}</a>`;

            stockHeader.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                const { ticker, name } = stock;
                const overviewPanel = document.getElementById('stock-overview-panel');
                if (overviewPanel) {
                    overviewPanel.style.display = 'block';
                    overviewPanel.innerHTML = `
                        <div class="overview-header"><h3>${name} (${ticker})</h3></div>
                        <div class="overview-stats">
                            <div class="stat-item">📰 <span>뉴스</span> <span class="count">${(stock.news || []).length}</span></div>
                            <div class="stat-item">📊 <span>리포트</span> <span class="count">${totalCount}</span></div>
                        </div>
                        <div class="overview-footer">
                            <button class="btn btn-primary btn-sm btn-go-detail">상세 이동</button>
                            <button class="btn btn-danger btn-sm" onclick="deleteStock('${ticker}')">제거</button>
                        </div>
                    `;
                    overviewPanel.querySelector('.btn-go-detail').onclick = () => {
                        history.pushState({ tab: 'dashboard', ticker, name }, '', `/stock/${ticker}`);
                        switchTab('dashboard-tab', false);
                        loadStockDashboard(ticker, name);
                    };
                }
            });
            childrenContainer.appendChild(stockHeader);
        });
    }

    nodeEl.appendChild(header);
    nodeEl.appendChild(childrenContainer);
    container.appendChild(nodeEl);
    if (depth < 1) { header.classList.add('expanded'); childrenContainer.classList.add('show'); }
}

export async function jumpToStock(ticker, boardName, path, loadBoardData) {
    const boardSelect = document.getElementById('board-select');
    if (boardSelect.value !== boardName) {
        boardSelect.value = boardName;
        window._currentBoardName = boardName;
        await loadBoardData(boardName);
    }
    const headers = document.querySelectorAll('.node-header.folder');
    path.forEach(nodeName => {
        headers.forEach(h => {
            if (h.innerText.includes(nodeName)) h.nextElementSibling.classList.add('show');
        });
    });
    setTimeout(() => {
        const stocks = document.querySelectorAll('.node-header.stock');
        for (const s of stocks) {
            if (s.innerText.includes(ticker)) {
                s.scrollIntoView({ behavior: 'smooth', block: 'center' });
                s.click();
                break;
            }
        }
    }, 100);
}

/**
 * 마인드맵 트리 초기화 (보드 목록 로드 및 이벤트 바인딩)
 * @param {Function} loadBoardData - 보드 데이터를 로드하는 콜백 함수
 */
export async function initTree(loadBoardData) {
    const boardSelect = document.getElementById('board-select');
    const loadBtn = document.getElementById('load-board-btn');

    if (!boardSelect || !loadBtn) return;

    try {
        // 1. 가용 보드 목록 가져오기
        const response = await fetch('/api/boards');
        const boards = await response.json();

        if (boards && boards.length > 0) {
            boardSelect.innerHTML = boards.map(b => `<option value="${b.id}">${b.name}</option>`).join('');
            
            // 초기 보드 로드 (첫 번째 항목의 ID 사용)
            const firstBoardId = boards[0].id;
            window._currentBoardName = firstBoardId;
            loadBoardData(firstBoardId);
        }

        // 2. 불러오기 버튼 이벤트
        loadBtn.onclick = () => {
            const selected = boardSelect.value;
            window._currentBoardName = selected;
            loadBoardData(selected);
        };

    } catch (err) {
        console.error('Failed to initialize tree boards:', err);
    }
}
