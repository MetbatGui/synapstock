/**
 * @fileoverview 마인드맵 관련 모달(노드/종목 추가) 관리 모듈.
 * @module ui/mindmap/modals
 */
import { addLogEntry } from '../tabs.js';

export let LAST_CLICKED_NODE_NAME = '';
export let SELECTED_STOCK = null;
export let SELECTED_STOCKS = [];

export function openModal(id) {
    document.getElementById(id).classList.add('show');
}

export function closeModal(id) {
    document.getElementById(id).classList.remove('show');
    if (id === 'add-stock-modal') {
        document.getElementById('autocomplete-results').style.display = 'none';
        document.getElementById('selected-stock-info').style.display = 'none';
        document.getElementById('confirm-add-stock').disabled = true;
        document.getElementById('confirm-add-stock').textContent = '확인';
        document.getElementById('stock-search-input').value = '';
        
        // ipo-quick-list 영역 초기화
        const ipoContainer = document.getElementById('ipo-quick-list');
        if (ipoContainer) {
            ipoContainer.innerHTML = '<div style="color: #64748b; font-size: 0.8rem; text-align: center; padding: 10px;">불러오는 중...</div>';
        }
        
        // 전체선택 버튼 숨기기
        const selectAllBtn = document.getElementById('ipo-btn-select-all');
        if (selectAllBtn) {
            selectAllBtn.style.display = 'none';
        }
        
        SELECTED_STOCK = null;
        SELECTED_STOCKS = [];
    } else if (id === 'add-node-modal') {
        document.getElementById('new-node-name').value = '';
    }
}

export function showAddNodeModal(parentName) {
    LAST_CLICKED_NODE_NAME = parentName;
    document.getElementById('parent-node-name').innerText = parentName;
    openModal('add-node-modal');
}

export async function showAddStockModal(targetName) {
    LAST_CLICKED_NODE_NAME = targetName;
    document.getElementById('target-node-name').innerText = targetName;
    openModal('add-stock-modal');

    SELECTED_STOCKS = [];

    // 신규상장주 목록 동적 로드
    const ipoContainer = document.getElementById('ipo-quick-list');
    const selectAllBtn = document.getElementById('ipo-btn-select-all');
    
    if (ipoContainer) {
        ipoContainer.innerHTML = '<div style="color: #64748b; font-size: 0.8rem; text-align: center; padding: 10px;">불러오는 중...</div>';
        try {
            // 2025년과 2026년 데이터를 병합하여 가져옴
            const years = ["2025", "2026"];
            const fetchPromises = years.map(yr => 
                fetch(`/api/statistics/new-listing?year=${yr}`).then(r => r.ok ? r.json() : { items: [] })
            );
            const results = await Promise.all(fetchPromises);
            const allIpos = results.flatMap(res => res.items || []);

            if (allIpos.length === 0) {
                ipoContainer.innerHTML = '<div style="color: #64748b; font-size: 0.8rem; text-align: center; padding: 10px;">신규상장주가 없습니다.</div>';
                if (selectAllBtn) selectAllBtn.style.display = 'none';
                return;
            }

            // 상장일(listing_date) 기반 가상 트리 빌드
            // 구조: { "2025년": [ ... ] }
            const groupedTree = {};
            allIpos.forEach(item => {
                if (item.status === 'ASSIGNED' || item.status === 'IGNORED') {
                    return;
                }
                const dateStr = (item.listing_date || "").replace(/\./g, "-");
                let yearStr = "기타";
                
                if (dateStr && dateStr.includes("-")) {
                    const parts = dateStr.split("-");
                    if (parts[0]) yearStr = parts[0] + "년";
                }
                
                if (!groupedTree[yearStr]) groupedTree[yearStr] = [];
                groupedTree[yearStr].push(item);
            });

            // 트리 DOM 렌더링
            let treeHtml = '';
            
            // 연도 기준 내림차순 정렬
            const sortedYears = Object.keys(groupedTree).sort((a, b) => b.localeCompare(a));
            
            sortedYears.forEach(year => {
                if (!groupedTree[year] || groupedTree[year].length === 0) return;
                treeHtml += `
                    <div class="ipo-quick-list-node">
                        <div class="ipo-quick-list-folder" data-target="folder-${year}">
                            <i class="fas fa-calendar-alt"></i> ${year}
                        </div>
                        <div class="ipo-quick-list-children" id="folder-${year}">
                `;
                
                // 종목 렌더링
                groupedTree[year].forEach(stock => {
                    const isAssigned = stock.status === 'ASSIGNED';
                    const statusText = isAssigned ? `배치완료 (${stock.current_board || '가상보드'})` : '미배치';
                    const assignedClass = isAssigned ? 'assigned' : '';
                    const disabledAttr = isAssigned ? 'disabled' : '';
                    
                    treeHtml += `
                        <div class="ipo-quick-list-stock ${assignedClass}" 
                             data-name="${stock.name}"
                             data-ticker="${stock.ticker}"
                             data-assigned="${isAssigned}">
                            <div class="ipo-quick-list-stock-info">
                                <input type="checkbox" class="ipo-quick-list-stock-checkbox" ${disabledAttr} 
                                       data-name="${stock.name}" data-ticker="${stock.ticker}" />
                                <i class="fas fa-file-invoice-dollar"></i>
                                <span class="ipo-quick-list-stock-name">${stock.name}</span>
                                <span class="ipo-quick-list-stock-ticker">${stock.ticker || ''}</span>
                            </div>
                            <span class="ipo-quick-list-stock-status">${statusText}</span>
                        </div>
                    `;
                });
                
                treeHtml += `
                        </div>
                    </div>
                `;
            });

            ipoContainer.innerHTML = treeHtml;

            // 아코디언 토글 이벤트 리스너 바인딩
            const folderElements = ipoContainer.querySelectorAll('.ipo-quick-list-folder');
            folderElements.forEach(folder => {
                folder.onclick = (e) => {
                    e.stopPropagation();
                    const targetId = folder.dataset.target;
                    const childrenDiv = document.getElementById(targetId);
                    if (childrenDiv) {
                        childrenDiv.classList.toggle('collapsed');
                        folder.classList.toggle('collapsed');
                    }
                };
            });

            // UI 갱신 헬퍼 함수
            const updateSelectionUI = () => {
                const infoBox = document.getElementById('selected-stock-info');
                const displaySpan = document.getElementById('selected-stock-display');
                const confirmBtn = document.getElementById('confirm-add-stock');
                
                if (SELECTED_STOCKS.length > 0) {
                    const s = SELECTED_STOCKS[0];
                    const hasValidTicker = s.ticker && s.ticker !== 'null' && s.ticker !== 'undefined';
                    const tickerStr = hasValidTicker ? ` (${s.ticker})` : '';
                    
                    if (SELECTED_STOCKS.length === 1) {
                        displaySpan.innerText = `${s.name}${tickerStr}`;
                    } else {
                        displaySpan.innerText = `${s.name}${tickerStr} 외 ${SELECTED_STOCKS.length - 1}개 종목`;
                    }
                    infoBox.style.display = 'block';
                    confirmBtn.disabled = false;
                    confirmBtn.textContent = `${SELECTED_STOCKS.length}개 종목 추가`;
                } else {
                    infoBox.style.display = 'none';
                    confirmBtn.disabled = true;
                    confirmBtn.textContent = '확인';
                }
            };

            const isSameStock = (s, name, ticker) => {
                const t1 = (ticker === 'null' || ticker === 'undefined' || !ticker) ? null : ticker;
                const t2 = (s.ticker === 'null' || s.ticker === 'undefined' || !s.ticker) ? null : s.ticker;
                if (t1 && t2) return t1 === t2;
                return s.name === name;
            };

            // 체크박스 및 종목 행 클릭 처리
            const stockElements = ipoContainer.querySelectorAll('.ipo-quick-list-stock');
            stockElements.forEach(row => {
                const checkbox = row.querySelector('.ipo-quick-list-stock-checkbox');
                
                const toggleStockSelection = (forceState) => {
                    if (row.dataset.assigned === 'true') return;
                    
                    const name = row.dataset.name;
                    const ticker = row.dataset.ticker;
                    
                    const isChecked = forceState !== undefined ? forceState : !checkbox.checked;
                    checkbox.checked = isChecked;
                    
                    if (isChecked) {
                        if (!SELECTED_STOCKS.some(s => isSameStock(s, name, ticker))) {
                            SELECTED_STOCKS.push({ name, ticker });
                        }
                    } else {
                        SELECTED_STOCKS = SELECTED_STOCKS.filter(s => !isSameStock(s, name, ticker));
                    }
                    updateSelectionUI();
                };

                // 행 클릭 시 (체크박스 자체 클릭이 아닐 때만 토글 실행하여 오버랩 방지)
                row.onclick = (e) => {
                    if (e.target !== checkbox) {
                        toggleStockSelection();
                    }
                };

                // 체크박스 직접 변경 시
                checkbox.onchange = () => {
                    toggleStockSelection(checkbox.checked);
                };
            });

            // 전체 선택 버튼 활성화 및 바인딩
            if (selectAllBtn) {
                const unassignedCheckboxes = Array.from(ipoContainer.querySelectorAll('.ipo-quick-list-stock-checkbox:not([disabled])'));
                if (unassignedCheckboxes.length > 0) {
                    selectAllBtn.style.display = 'block';
                    selectAllBtn.onclick = () => {
                        // 모든 미배치 종목이 이미 선택되어 있다면 전체 해제, 아니라면 전체 선택
                        const allChecked = unassignedCheckboxes.every(cb => cb.checked);
                        unassignedCheckboxes.forEach(cb => {
                            const name = cb.dataset.name;
                            const ticker = cb.dataset.ticker;
                            
                            const newState = !allChecked;
                            cb.checked = newState;
                            
                            if (newState) {
                                if (!SELECTED_STOCKS.some(s => isSameStock(s, name, ticker))) {
                                    SELECTED_STOCKS.push({ name, ticker });
                                }
                            } else {
                                SELECTED_STOCKS = SELECTED_STOCKS.filter(s => !isSameStock(s, name, ticker));
                            }
                        });
                        updateSelectionUI();
                    };
                } else {
                    selectAllBtn.style.display = 'none';
                }
            }

        } catch (err) {
            console.error('Failed to load IPO quick list:', err);
            ipoContainer.innerHTML = '<div style="color: #ef4444; font-size: 0.8rem; text-align: center; padding: 10px;">오류 발생</div>';
        }
    }
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
                            SELECTED_STOCKS = [{ name: item.name, ticker: item.ticker }];
                            document.getElementById('selected-stock-display').innerText = `${SELECTED_STOCK.name} (${SELECTED_STOCK.ticker})`;
                            document.getElementById('selected-stock-info').style.display = 'block';
                            document.getElementById('confirm-add-stock').disabled = false;
                            document.getElementById('confirm-add-stock').textContent = '1개 종목 추가';
                            resultsContainer.style.display = 'none';
                            searchInput.value = SELECTED_STOCK.name;

                            // 신규상장주 목록에 표시된 체크박스들 모두 해제
                            const checkboxes = document.querySelectorAll('.ipo-quick-list-stock-checkbox');
                            checkboxes.forEach(cb => cb.checked = false);
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
        if (SELECTED_STOCKS.length === 0) return;
        const currentBoard = document.getElementById('board-select').value;
        const confirmBtn = document.getElementById('confirm-add-stock');
        confirmBtn.disabled = true;
        confirmBtn.textContent = '추가 중...';

        try {
            // 다중 종목 비동기 배치 연달아 추가
            const addPromises = SELECTED_STOCKS.map(stock => 
                fetch(`/api/stock/add?board=${encodeURIComponent(currentBoard)}&parent=${encodeURIComponent(LAST_CLICKED_NODE_NAME)}&name=${encodeURIComponent(stock.name)}&ticker=${encodeURIComponent(stock.ticker)}`, { method: 'POST' })
            );
            const results = await Promise.all(addPromises);
            const successCount = results.filter(res => res.ok).length;
            
            if (successCount > 0) {
                addLogEntry(`[SYSTEM] 종목 일괄 추가 완료 (${successCount}/${SELECTED_STOCKS.length}개 성공)`, 'success');
            } else {
                addLogEntry(`[SYSTEM] 종목 추가 실패`, 'error');
            }
        } catch (err) {
            console.error('Batch add failed:', err);
            addLogEntry(`[SYSTEM] 종목 추가 중 오류 발생`, 'error');
        } finally {
            confirmBtn.textContent = '확인';
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
