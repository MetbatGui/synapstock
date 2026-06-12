/**
 * @fileoverview 마인드맵 전역 액션(Miro 동기화, 전종목 검색) 모듈.
 * @module ui/mindmap/actions
 */
import { addLogEntry } from '../tabs.js';

/**
 * Miro 동기화 버튼 클릭 이벤트를 초기화합니다.
 */
export function initSyncButton() {
    const syncBtn = document.getElementById('sync-btn');
    if (!syncBtn) return;
    
    syncBtn.addEventListener('click', async () => {
        if (!window._currentBoardName) {
            addLogEntry('[WARN] 동기화할 보드가 로드되지 않았습니다.', 'error');
            return;
        }

        addLogEntry(`[API] Miro 동기화 요청: ${window._currentBoardName}...`, 'system');

        try {
            const response = await fetch(`/api/sync?name=${window._currentBoardName}`, { method: 'POST' });
            const data = await response.json();
            if (data.status === 'started') {
                addLogEntry(`[SYSTEM] '${window._currentBoardName}' 동기화 작업이 백그라운드에서 시작되었습니다.`, 'info');
            }
        } catch (err) {
            addLogEntry(`[ERROR] 동기화 요청 실패: ${err.message}`, 'error');
        }
    });
}

/**
 * 전종목 데이터를 캐싱하고 전역 검색 기능을 초기화합니다.
 */
export async function initGlobalSearch(jumpToStock) {
    const searchInput = document.getElementById('global-stock-search');
    const resultsContainer = document.getElementById('global-search-results');

    if (!searchInput) return;

    try {
        const response = await fetch('/api/stocks/all');
        window._globalStockCache = await response.json();
        addLogEntry(`[SYSTEM] 총 ${window._globalStockCache.length}개의 종목 데이터를 캐싱했습니다.`, 'success');
    } catch (err) {
        console.error('Global search cache failed:', err);
    }

    searchInput.addEventListener('input', (e) => {
        const query = e.target.value.trim().toLowerCase();
        if (query.length < 1) {
            resultsContainer.style.display = 'none';
            return;
        }

        const filtered = (window._globalStockCache || []).filter(s =>
            s.name.toLowerCase().includes(query) || s.ticker.toLowerCase().includes(query)
        ).slice(0, 10);

        if (filtered.length > 0) {
            resultsContainer.innerHTML = '';
            filtered.forEach(item => {
                const div = document.createElement('div');
                div.className = 'search-result-item';
                div.innerHTML = `
                    <span class="search-result-name">${item.name} (${item.ticker})</span>
                    <div class="search-result-meta">
                        <span class="search-result-board">${item.board_name || item.board.replace('theme_', '').replace('virtual_', '').replace('.json', '')}</span>
                        <span class="search-result-path">${item.path.join(' > ')}</span>
                    </div>
                `;
                div.onclick = () => {
                    searchInput.value = item.name;
                    resultsContainer.style.display = 'none';
                    jumpToStock(item.ticker, item.board, item.path, item.name);
                };
                resultsContainer.appendChild(div);
            });
            resultsContainer.style.display = 'block';
        } else {
            resultsContainer.style.display = 'none';
        }
    });

    document.addEventListener('click', (e) => {
        if (!searchInput.contains(e.target) && !resultsContainer.contains(e.target)) {
            resultsContainer.style.display = 'none';
        }
    });
}
