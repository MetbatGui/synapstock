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

    // 가상보드의 연도 노드(예: 2025년, 2026년)인지 여부 판별
    const isVirtualYearNode = window._currentBoardName === "virtual_신규상장주" && /^\d{4}년$/.test(node.name);

    let footerButtonsHtml = '';
    if (isVirtualYearNode) {
        footerButtonsHtml = `<button class="btn btn-danger btn-sm" onclick="deleteNode('${node.name}')" style="background:#ef4444;color:white;">일괄 제거</button>`;
    } else {
        const addNodeBtn = `<button class="btn btn-secondary btn-sm" onclick="showAddNodeModal('${node.name}')">새 노드</button>`;
        const addStockBtn = `<button class="btn btn-secondary btn-sm" onclick="showAddStockModal('${node.name}')">종목 추가</button>`;
        const deleteBtn = !isRoot ? `<button class="btn btn-danger btn-sm" onclick="deleteNode('${node.name}')" style="background:#ef4444;color:white;">제거</button>` : '';
        footerButtonsHtml = `${addNodeBtn} ${addStockBtn} ${deleteBtn}`;
    }

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
            ${footerButtonsHtml}
        </div>
    `;
    addLogEntry(`[UI] 노드 선택됨: ${node.name}`, 'info');
}

export function renderNode(node, container, depth, globalLocalReportCounts, currentBoardData, loadStockDashboard, loadBoardData) {
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
        node.nodes.forEach(child => renderNode(child, childrenContainer, depth + 1, globalLocalReportCounts, currentBoardData, loadStockDashboard, loadBoardData));
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

                    // 가상보드 신규상장주이고, 배치 완료 상태인 경우 "보드로 이동" 버튼 활성화
                    const isIpoAssigned = currentBoardData && (currentBoardData.name === "신규상장주" || window._currentBoardName === "virtual_신규상장주") && stock.status === "ASSIGNED" && stock.current_board && stock.current_board !== "virtual_신규상장주";
                    const jumpBtnHtml = isIpoAssigned ? `<button class="btn btn-success btn-sm btn-jump" style="background:#22c55e;color:white;border:none;">보드로 이동</button>` : '';

                    // 가상보드 신규상장주이고, 미배치 상태(PENDING)인 경우 "분류" 버튼 활성화
                    const isIpoPending = currentBoardData && (currentBoardData.name === "신규상장주" || window._currentBoardName === "virtual_신규상장주") && stock.status === "PENDING";
                    const assignBtnHtml = isIpoPending ? `<button class="btn btn-warning btn-sm btn-assign" style="background:#f59e0b;color:white;border:none;">분류</button>` : '';

                    overviewPanel.innerHTML = `
                        <div class="overview-header"><h3>${name} (${ticker})</h3></div>
                        <div class="overview-stats">
                            <div class="stat-item">📰 <span>뉴스</span> <span class="count">${(stock.news || []).length}</span></div>
                            <div class="stat-item">📊 <span>리포트</span> <span class="count">${totalCount}</span></div>
                        </div>
                        <div class="overview-footer" style="display:flex; gap:5px; flex-wrap:wrap;">
                            <button class="btn btn-primary btn-sm btn-go-detail">상세 이동</button>
                            ${jumpBtnHtml}
                            ${assignBtnHtml}
                            <button class="btn btn-danger btn-sm" onclick="deleteStock('${ticker}')">제거</button>
                        </div>
                    `;
                    overviewPanel.querySelector('.btn-go-detail').onclick = () => {
                        history.pushState({ tab: 'dashboard', ticker, name }, '', `/stock/${ticker}`);
                        switchTab('dashboard-tab', false);
                        loadStockDashboard(ticker, name);
                    };

                    if (isIpoAssigned) {
                        overviewPanel.querySelector('.btn-jump').onclick = async () => {
                            if (loadBoardData) {
                                await jumpToStock(ticker, stock.current_board, stock.current_path, loadBoardData);
                            } else {
                                alert("보드 데이터를 불러올 수 없습니다.");
                            }
                        };
                    }

                    if (isIpoPending) {
                        overviewPanel.querySelector('.btn-assign').onclick = async () => {
                            await showAssignModal(ticker, name, loadBoardData);
                        };
                    }
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

export async function showAssignModal(ticker, name, loadBoardData) {
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
                종목 <strong>[${name} (${ticker})]</strong>을(를) 에벤에셀 보드에 할당합니다.
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
    function updateCurrentPath() {
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
    }

    // 하위 자식이 존재하는지 확인하고, 있으면 다음 뎁스의 선택 상자를 생성하는 함수
    function createNextLevel(parentNode, depth) {
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
    }

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

                // Step 2: 타겟 보드에 추가
                const addRes = await fetch(`/api/stock/add?board=${selectedBoard}&parent=${encodeURIComponent(selectedNode)}&name=${encodeURIComponent(name)}&ticker=${ticker}`, { method: 'POST' });
                if (!addRes.ok) throw new Error('테마 보드 추가 실패');

                alert(`종목 [${name}]이 [${boardSelect.options[boardSelect.selectedIndex].text} > ${selectedNode}] 보드에 성공적으로 배치되었습니다.`);
                closeModal();
                if (loadBoardData) {
                    await loadBoardData(window._currentBoardName);
                }
            } catch (err) {
                alert(`배치 오류: ${err.message}`);
                confirmBtn.disabled = false;
                confirmBtn.textContent = '배치 확정';
            }
        };

    } catch (e) {
        boardSelect.innerHTML = '<option value="">보드 조회 실패</option>';
        console.error(e);
    }
}
