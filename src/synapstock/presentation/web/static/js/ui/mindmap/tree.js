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
                    const isIpoAssigned = currentBoardData && currentBoardData.name === "신규상장주" && stock.status === "ASSIGNED" && stock.current_board && stock.current_board !== "virtual_신규상장주";
                    const jumpBtnHtml = isIpoAssigned ? `<button class="btn btn-success btn-sm btn-jump" style="background:#22c55e;color:white;border:none;">보드로 이동</button>` : '';

                    // 가상보드 신규상장주이고, 미배치 상태(PENDING)인 경우 "분류" 버튼 활성화
                    const isIpoPending = currentBoardData && currentBoardData.name === "신규상장주" && stock.status === "PENDING";
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
        <div class="ipo-modal" style="position:fixed;top:50%;left:50%;transform:translate(-50%, -50%);background:#1e293b;padding:25px;border-radius:12px;z-index:99999;box-shadow:0 10px 25px rgba(0,0,0,0.5);width:360px;color:white;border:1px solid #334155;">
            <h3 style="margin-top:0;font-size:1.1rem;display:flex;align-items:center;gap:8px;"><i class="fas fa-th-large" style="color:#3b82f6;"></i> 신규상장주 보드 배치</h3>
            <p style="font-size:0.85rem; color:#94a3b8; margin-bottom:20px;">
                종목 <strong>[${name} (${ticker})]</strong>을(를) 마인드맵 보드에 할당합니다.
            </p>
            
            <div class="ipo-modal-field" style="margin-bottom:15px;">
                <label style="display:block;font-size:0.8rem;color:#94a3b8;margin-bottom:5px;">대상 테마 보드</label>
                <select id="ipo-board-select" class="ipo-modal-select" style="width:100%;padding:8px;background:#0f172a;border:1px solid #334155;border-radius:6px;color:white;">
                    <option value="">보드를 불러오는 중...</option>
                </select>
            </div>
            
            <div class="ipo-modal-field" style="margin-bottom:20px;">
                <label style="display:block;font-size:0.8rem;color:#94a3b8;margin-bottom:5px;">배치할 섹터(부모) 노드</label>
                <select id="ipo-node-select" class="ipo-modal-select" disabled style="width:100%;padding:8px;background:#0f172a;border:1px solid #334155;border-radius:6px;color:white;opacity:0.5;">
                    <option value="">보드를 먼저 선택해 주세요.</option>
                </select>
            </div>
            
            <div class="ipo-modal-footer" style="display:flex;justify-content:flex-end;gap:10px;">
                <button id="ipo-btn-cancel" class="ipo-modal-btn cancel" style="padding:6px 12px;background:#475569;color:white;border:none;border-radius:6px;cursor:pointer;">취소</button>
                <button id="ipo-btn-confirm" class="ipo-modal-btn confirm" disabled style="padding:6px 12px;background:#3b82f6;color:white;border:none;border-radius:6px;cursor:pointer;">배치 확정</button>
            </div>
        </div>
    `;

    // 백그라운드 클릭 차단을 위한 뒷배경 오버레이 스타일 부여
    overlay.style.position = 'fixed';
    overlay.style.top = '0';
    overlay.style.left = '0';
    overlay.style.width = '100%';
    overlay.style.height = '100%';
    overlay.style.background = 'rgba(0,0,0,0.6)';
    overlay.style.backdropFilter = 'blur(4px)';
    overlay.style.zIndex = '99998';

    document.body.appendChild(overlay);

    const boardSelect = document.getElementById('ipo-board-select');
    const nodeSelect = document.getElementById('ipo-node-select');
    const confirmBtn = document.getElementById('ipo-btn-confirm');
    const cancelBtn = document.getElementById('ipo-btn-cancel');

    // 모달 닫기 함수
    const closeModal = () => overlay.remove();
    cancelBtn.onclick = closeModal;
    overlay.onclick = (e) => { if (e.target === overlay) closeModal(); };

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
            if (!selectedBoard) {
                nodeSelect.innerHTML = '<option value="">보드를 먼저 선택해 주세요.</option>';
                nodeSelect.disabled = true;
                nodeSelect.style.opacity = '0.5';
                confirmBtn.disabled = true;
                return;
            }

            nodeSelect.innerHTML = '<option value="">노드를 불러오는 중...</option>';
            nodeSelect.disabled = true;
            nodeSelect.style.opacity = '0.5';
            
            try {
                const resTree = await fetch(`/api/board?name=${selectedBoard}`);
                const treeData = await resTree.json();
                
                const flatNodes = [];
                const extractNodes = (node) => {
                    if (node.name) flatNodes.push(node.name);
                    if (node.nodes) node.nodes.forEach(extractNodes);
                };
                extractNodes(treeData);

                nodeSelect.innerHTML = '<option value="">-- 노드 선택 --</option>';
                flatNodes.forEach(n => {
                    const opt = document.createElement('option');
                    opt.value = n;
                    opt.textContent = n;
                    nodeSelect.appendChild(opt);
                });
                
                nodeSelect.disabled = false;
                nodeSelect.style.opacity = '1.0';
            } catch (e) {
                nodeSelect.innerHTML = '<option value="">노드 조회 실패</option>';
                console.error(e);
            }
        };

        // 3. 노드 선택에 따른 배치 확정 활성화
        nodeSelect.onchange = () => {
            confirmBtn.disabled = !nodeSelect.value;
        };

        // 4. 배치 확정 처리
        confirmBtn.onclick = async () => {
            const selectedBoard = boardSelect.value;
            const selectedNode = nodeSelect.value;
            
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
