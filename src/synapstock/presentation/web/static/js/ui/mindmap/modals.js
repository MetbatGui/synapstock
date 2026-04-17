/**
 * @fileoverview 마인드맵 관련 모달(노드/종목 추가) 관리 모듈.
 * @module ui/mindmap/modals
 */
import { addLogEntry } from '../tabs.js';

export let LAST_CLICKED_NODE_NAME = '';
export let SELECTED_STOCK = null;

export function openModal(id) {
    document.getElementById(id).classList.add('show');
}

export function closeModal(id) {
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

export function showAddNodeModal(parentName) {
    LAST_CLICKED_NODE_NAME = parentName;
    document.getElementById('parent-node-name').innerText = parentName;
    openModal('add-node-modal');
}

export function showAddStockModal(targetName) {
    LAST_CLICKED_NODE_NAME = targetName;
    document.getElementById('target-node-name').innerText = targetName;
    openModal('add-stock-modal');
}

export function initMindmapModals(loadBoardData) {
    // 자동완성
    const searchInput = document.getElementById('stock-search-input');
    const resultsContainer = document.getElementById('autocomplete-results');

    if (searchInput) {
        searchInput.addEventListener('input', async (e) => {
            const query = e.target.value.trim();
            if (query.length < 2) { resultsContainer.style.display = 'none'; return; }
            try {
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
                }
            } catch (err) { console.error('Autocomplete failed:', err); }
        });
    }

    // 노드 추가 확인
    document.getElementById('confirm-add-node').onclick = async () => {
        const name = document.getElementById('new-node-name').value.trim();
        if (!name) return;
        const currentBoard = document.getElementById('board-select').value;
        const res = await fetch(`/api/node/add?board=${encodeURIComponent(currentBoard)}&parent=${encodeURIComponent(LAST_CLICKED_NODE_NAME)}&name=${encodeURIComponent(name)}`, { method: 'POST' });
        if (res.ok) {
            addLogEntry(`[SYSTEM] 노드 추가 성공: ${name}`, 'success');
            closeModal('add-node-modal');
            loadBoardData(window._currentBoardName);
        }
    };

    // 종목 추가 확인
    document.getElementById('confirm-add-stock').onclick = async () => {
        if (!SELECTED_STOCK) return;
        const currentBoard = document.getElementById('board-select').value;
        const res = await fetch(`/api/stock/add?board=${encodeURIComponent(currentBoard)}&parent=${encodeURIComponent(LAST_CLICKED_NODE_NAME)}&name=${encodeURIComponent(SELECTED_STOCK.name)}&ticker=${encodeURIComponent(SELECTED_STOCK.ticker)}`, { method: 'POST' });
        if (res.ok) {
            addLogEntry(`[SYSTEM] 종목 추가 성공: ${SELECTED_STOCK.name}`, 'success');
            closeModal('add-stock-modal');
            loadBoardData(window._currentBoardName);
        }
    };
}

export async function deleteNode(nodeName, loadBoardData) {
    if (!confirm(`'${nodeName}' 노드를 삭제하시겠습니까?`)) return;
    const currentBoard = document.getElementById('board-select').value;
    const res = await fetch(`/api/node/delete?board=${encodeURIComponent(currentBoard)}&name=${encodeURIComponent(nodeName)}`, { method: 'DELETE' });
    if (res.ok) {
        addLogEntry(`[SYSTEM] 노드 삭제 완료: ${nodeName}`, 'success');
        document.getElementById('stock-overview-panel').style.display = 'none';
        loadBoardData(window._currentBoardName);
    }
}

export async function deleteStock(ticker, loadBoardData) {
    if (!confirm(`'${ticker}' 종목을 제거하시겠습니까?`)) return;
    const currentBoard = document.getElementById('board-select').value;
    const res = await fetch(`/api/stock/delete?board=${encodeURIComponent(currentBoard)}&ticker=${encodeURIComponent(ticker)}`, { method: 'DELETE' });
    if (res.ok) {
        addLogEntry(`[SYSTEM] 종목 제거 완료: ${ticker}`, 'success');
        document.getElementById('stock-overview-panel').style.display = 'none';
        loadBoardData(window._currentBoardName);
    }
}
