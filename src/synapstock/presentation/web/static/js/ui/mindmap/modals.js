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
            const results = [];
            const errorMessages = [];

            // 순차적으로 종목을 추가하며 결과 체크 (중복 에러 피드백 수집)
            for (const stock of SELECTED_STOCKS) {
                const url = `/api/stock/add?board=${encodeURIComponent(currentBoard)}&parent=${encodeURIComponent(LAST_CLICKED_NODE_NAME)}&name=${encodeURIComponent(stock.name)}&ticker=${encodeURIComponent(stock.ticker)}`;
                const res = await fetch(url, { method: 'POST' });
                if (res.ok) {
                    results.push(res);
                } else if (res.status === 409) {
                    const errData = await res.json();
                    errorMessages.push(errData.message);
                } else {
                    errorMessages.push(`[${stock.name}] 추가 중 오류 발생`);
                }
            }
            
            const successCount = results.length;
            if (successCount > 0) {
                addLogEntry(`[SYSTEM] 종목 추가 완료 (${successCount}/${SELECTED_STOCKS.length}개 성공)`, 'success');
            }
            if (errorMessages.length > 0) {
                alert(errorMessages.join('\n'));
                addLogEntry(`[SYSTEM] 일부 종목 추가 실패:\n${errorMessages.join('\n')}`, 'error');
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
    const currentBoard = document.getElementById('board-select').value;
    
    // 가상보드의 가상 연도 노드(2025년, 2026년 등) 삭제 시도 시 일괄 무시 모달로 가로챔
    if (currentBoard === "virtual_신규상장주" && /^\d{4}년$/.test(nodeName)) {
        showBatchIgnoreModal(nodeName, loadBoardData);
        return;
    }

    if (!confirm(`'${nodeName}' 노드를 삭제하시겠습니까?`)) return;
    const res = await fetch(`/api/node/delete?board=${encodeURIComponent(currentBoard)}&name=${encodeURIComponent(nodeName)}`, { method: 'DELETE' });
    if (res.ok) {
        addLogEntry(`[SYSTEM] 노드 삭제 완료: ${nodeName}`, 'success');
        document.getElementById('stock-overview-panel').style.display = 'none';
        loadBoardData(window._currentBoardName);
    }
}

export function showBatchIgnoreModal(yearNodeName, loadBoardData) {
    if (!window._currentBoardData) {
        alert("보드 데이터를 불러오지 못했습니다. 잠시 후 다시 시도하십시오.");
        return;
    }

    const yearNode = window._currentBoardData.nodes.find(n => n.name === yearNodeName);
    if (!yearNode || !yearNode.stocks || yearNode.stocks.length === 0) {
        alert(`'${yearNodeName}' 에 등록된 대기 종목이 없습니다.`);
        return;
    }

    // PENDING 또는 상태가 지정되지 않은 대기 종목 추출
    const pendingStocks = yearNode.stocks.filter(s => s.status === "PENDING" || !s.status);
    if (pendingStocks.length === 0) {
        alert(`'${yearNodeName}' 에 제거 가능한 대기 종목이 없습니다.`);
        return;
    }

    // 모달 오버레이 생성
    const existing = document.getElementById('batch-ignore-modal-overlay');
    if (existing) existing.remove();

    const overlay = document.createElement('div');
    overlay.id = 'batch-ignore-modal-overlay';
    overlay.className = 'ipo-modal-overlay';
    overlay.style.zIndex = '2000';

    let listHtml = '';
    pendingStocks.forEach(s => {
        listHtml += `
            <div style="display:flex; align-items:center; gap:10px; margin-bottom:8px; background:rgba(255,255,255,0.02); padding:8px 12px; border-radius:8px; border:1px solid rgba(255,255,255,0.05);">
                <input type="checkbox" class="batch-ignore-checkbox" data-ticker="${s.ticker}" style="transform:scale(1.2); cursor:pointer;" />
                <span style="font-weight:600; color:#e2e8f0; font-size:0.9rem;">${s.name}</span>
                <span style="color:#64748b; font-size:0.8rem; font-family:monospace;">(${s.ticker})</span>
            </div>
        `;
    });

    overlay.innerHTML = `
        <div class="ipo-modal" style="max-width: 450px;">
            <h3><i class="fas fa-trash-alt" style="color:#ef4444; margin-right:8px;"></i> ${yearNodeName} 일괄 제거</h3>
            <p style="font-size:0.85rem; color:#94a3b8; margin-bottom:15px;">
                대기 목록에서 일괄 제거할 종목들을 선택해주세요. <br/>제거된 종목은 향후 동기화 시 다시 대기열에 들어오지 않습니다.
            </p>
            
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                <span style="font-size:0.8rem; color:#64748b;">선택 대상</span>
                <button id="batch-ignore-toggle-all" style="background:none; border:none; color:#3b82f6; font-size:0.8rem; cursor:pointer; font-weight:600;"><i class="fas fa-check-double"></i> 전체선택/해제</button>
            </div>
 
            <div style="max-height: 250px; overflow-y: auto; padding-right:5px; margin-bottom:20px;" id="batch-ignore-list-container">
                ${listHtml}
            </div>

            <div class="ipo-modal-footer">
                <button id="batch-ignore-btn-cancel" class="ipo-modal-btn cancel">취소</button>
                <button id="batch-ignore-btn-confirm" class="ipo-modal-btn confirm" style="background:#ef4444; color:white;">선택 항목 제거</button>
            </div>
        </div>
    `;

    document.body.appendChild(overlay);

    const cbs = overlay.querySelectorAll('.batch-ignore-checkbox');
    const toggleAllBtn = document.getElementById('batch-ignore-toggle-all');
    const confirmBtn = document.getElementById('batch-ignore-btn-confirm');
    const cancelBtn = document.getElementById('batch-ignore-btn-cancel');

    // 전체 토글 기능
    toggleAllBtn.onclick = () => {
        const anyChecked = Array.from(cbs).some(cb => cb.checked);
        cbs.forEach(cb => cb.checked = !anyChecked);
    };

    const closeModal = () => overlay.remove();
    cancelBtn.onclick = closeModal;
    overlay.onclick = (e) => { if (e.target === overlay) closeModal(); };

    confirmBtn.onclick = async () => {
        const selectedTickers = Array.from(cbs)
            .filter(cb => cb.checked)
            .map(cb => cb.dataset.ticker);

        if (selectedTickers.length === 0) {
            alert("제거할 종목이 선택되지 않았습니다.");
            return;
        }

        confirmBtn.disabled = true;
        confirmBtn.textContent = "제거 중...";

        try {
            const response = await fetch('/api/board/virtual/batch-ignore', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ tickers: selectedTickers })
            });

            if (response.ok) {
                addLogEntry(`[SYSTEM] 가상보드 일괄 제거 완료 (${selectedTickers.length}개 종목 제거)`, 'success');
                closeModal();
                loadBoardData(window._currentBoardName);
            } else {
                throw new Error("API 요청 실패");
            }
        } catch (e) {
            alert(`일괄 제거 중 오류 발생: ${e.message}`);
            confirmBtn.disabled = false;
            confirmBtn.textContent = "선택 항목 제거";
        }
    };
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
