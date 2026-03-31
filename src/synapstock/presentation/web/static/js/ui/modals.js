/**
 * @fileoverview 종목·노드 추가/삭제 모달, 전체 검색, Miro 동기화 버튼 UI 모듈.
 * @module ui/modals
 */
import { addLogEntry } from './tabs.js';

// ── 모달 기본 함수 ──────────────────────────────────────────────────────────

/**
 * 지정된 ID의 모달 요소에 `show` 클래스를 추가하여 표시합니다.
 *
 * @param {string} id - 열 모달 요소의 HTML `id`.
 * @returns {void}
 */
export function openModal(id) {
    document.getElementById(id).classList.add('show');
}

/**
 * 지정된 ID의 모달을 닫고 관련 입력 필드를 초기화합니다.
 *
 * - `add-stock-modal`: 자동완성 결과, 선택 정보, 검색 입력을 초기화합니다.
 * - `add-node-modal`: 노드 이름 입력을 초기화합니다.
 *
 * @param {string} id - 닫을 모달 요소의 HTML `id`.
 * @returns {void}
 */
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

// ── 모달 내부 상태 변수 ──────────────────────────────────────────────────────

/** @type {string} 마지막으로 클릭된 노드 이름. 노드/종목 추가 시 부모 대상으로 사용됩니다. */
export let LAST_CLICKED_NODE_NAME = '';

/** @type {{name: string, ticker: string}|null} 종목 추가 모달에서 선택된 종목 정보. */
export let SELECTED_STOCK = null;

/** @type {string} 리포트 업로드 대상 종목 티커. */
export let CURRENT_UPLOAD_TICKER = '';

/** @type {string} 뉴스 추가 대상 종목 티커. */
export let CURRENT_NEWS_TICKER = '';

/** @type {{title: string, date: string, url: string}|null} 뉴스 URL 스크래핑 결과 캐시. */
export let SCRAPED_NEWS_DATA = null;

// ── 모달 열기 함수 ──────────────────────────────────────────────────────────

/**
 * 노드 추가 모달을 열고 부모 노드 이름을 표시합니다.
 *
 * @param {string} parentName - 새 노드가 추가될 부모 노드 이름.
 * @returns {void}
 */
export function showAddNodeModal(parentName) {
    LAST_CLICKED_NODE_NAME = parentName;
    document.getElementById('parent-node-name').innerText = parentName;
    openModal('add-node-modal');
}

/**
 * 종목 추가 모달을 열고 대상 노드 이름을 표시합니다.
 *
 * @param {string} targetName - 종목이 추가될 노드 이름.
 * @returns {void}
 */
export function showAddStockModal(targetName) {
    LAST_CLICKED_NODE_NAME = targetName;
    document.getElementById('target-node-name').innerText = targetName;
    openModal('add-stock-modal');
}

/**
 * 뉴스 추가 모달을 열고 입력 필드를 초기화합니다.
 *
 * @param {string} ticker - 뉴스를 추가할 종목 티커.
 * @param {string} name - 모달에 표시할 종목명.
 * @returns {void}
 */
export function triggerNewsAdd(ticker, name) {
    CURRENT_NEWS_TICKER = ticker;
    SCRAPED_NEWS_DATA = null;
    document.getElementById('news-target-stock').innerText = name;
    document.getElementById('news-url-input').value = '';
    document.getElementById('news-scrape-preview').style.display = 'none';
    document.getElementById('confirm-add-news').disabled = true;
    openModal('add-news-modal');
}

/**
 * 숨겨진 파일 입력창(`#report-upload-input`)을 클릭하여 PDF 업로드를 트리거합니다.
 *
 * @param {string} ticker - 리포트를 업로드할 종목 티커.
 * @returns {void}
 */
export function triggerReportUpload(ticker) {
    CURRENT_UPLOAD_TICKER = ticker;
    const input = document.getElementById('report-upload-input');
    if (input) {
        input.value = '';
        input.click();
    }
}

// ── 삭제 함수 ───────────────────────────────────────────────────────────────

/**
 * 사용자 확인 후 노드를 삭제하고 자식 항목을 부모 노드로 흡수합니다.
 *
 * @param {string} nodeName - 삭제할 노드 이름.
 * @param {function(string): Promise<void>} loadBoardData - 삭제 후 트리를 갱신하는 함수.
 * @returns {Promise<void>}
 */
export async function deleteNode(nodeName, loadBoardData) {
    if (!confirm(`'${nodeName}' 노드를 삭제하시겠습니까?\n하위 노드와 종목은 상위 노드로 흡수됩니다.`)) return;

    const currentBoard = document.getElementById('board-select').value;
    const res = await fetch(`/api/node/delete?board=${encodeURIComponent(currentBoard)}&name=${encodeURIComponent(nodeName)}`, { method: 'DELETE' });
    if (res.ok) {
        addLogEntry(`[SYSTEM] 노드 삭제 및 흡수 완료: ${nodeName}`, 'success');
        document.getElementById('stock-overview-panel').style.display = 'none';
        loadBoardData(window._currentBoardName);
    }
}

/**
 * 사용자 확인 후 현재 보드에서 종목을 제거합니다.
 *
 * @param {string} ticker - 제거할 종목 티커 심볼.
 * @param {function(string): Promise<void>} loadBoardData - 제거 후 트리를 갱신하는 함수.
 * @returns {Promise<void>}
 */
export async function deleteStock(ticker, loadBoardData) {
    if (!confirm(`'${ticker}' 종목을 보드에서 제거하시겠습니까?`)) return;

    const currentBoard = document.getElementById('board-select').value;
    const res = await fetch(`/api/stock/delete?board=${encodeURIComponent(currentBoard)}&ticker=${encodeURIComponent(ticker)}`, { method: 'DELETE' });
    if (res.ok) {
        addLogEntry(`[SYSTEM] 종목 제거 완료: ${ticker}`, 'success');
        document.getElementById('stock-overview-panel').style.display = 'none';
        loadBoardData(window._currentBoardName);
    } else {
        addLogEntry(`[ERROR] 종목 제거 실패: ${ticker}`, 'error');
    }
}

// ── 초기화 함수 ─────────────────────────────────────────────────────────────

/**
 * Miro 동기화 버튼(`#sync-btn`)의 클릭 이벤트를 초기화합니다.
 *
 * 클릭 시 현재 로드된 보드(`window._currentBoardName`)를 기준으로
 * `/api/sync` 엔드포인트에 POST 요청을 전송합니다.
 *
 * @returns {void}
 */
export function initSyncButton() {
    const syncBtn = document.getElementById('sync-btn');
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
 * 전종목 데이터를 서버에서 가져와 캐싱하고, 검색 입력 이벤트를 초기화합니다.
 *
 * `/api/stocks/all` 로 전종목 목록을 가져와 `window._globalStockCache`에 저장합니다.
 * 입력값이 1자 이상일 때 이름/티커 필터링 결과를 드롭다운으로 표시합니다.
 *
 * @param {function(string, string, string[]): Promise<void>} jumpToStock
 *     종목 선택 시 해당 위치로 이동하는 함수.
 *     인자: `(ticker, boardName, path)`.
 * @returns {Promise<void>}
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
        console.error('Failed to fetch all stocks:', err);
        addLogEntry('[ERROR] 전종목 데이터 캐싱 실패', 'error');
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

    document.addEventListener('click', (e) => {
        if (!searchInput.contains(e.target) && !resultsContainer.contains(e.target)) {
            resultsContainer.style.display = 'none';
        }
    });
}

/**
 * 모달 내부 이벤트(자동완성, 노드/종목/뉴스 확인 버튼)를 초기화합니다.
 *
 * @param {function(string): Promise<void>} loadBoardData - 보드 데이터 재로드 함수.
 * @param {function(string, function, function, Object): Promise<void>} fetchNews - 뉴스 목록 렌더링 함수.
 * @param {function(string): Promise<Object|null>} fetchStockInfo - 종목 정보 조회 함수.
 * @param {Object<string, number>} globalLocalReportCounts - 종목명 키의 로컬 리포트 수량 맵.
 * @returns {void}
 */
export function initModalEvents(loadBoardData, fetchNews, fetchStockInfo, globalLocalReportCounts) {
    // 네이버 자동완성
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
                console.error('Autocomplete failed:', err);
            }
        });
    }

    // 노드 추가 확인 버튼
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

    // 종목 추가 확인 버튼
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

    // 뉴스 URL 자동 스크래핑
    const urlInput = document.getElementById('news-url-input');
    const previewBox = document.getElementById('news-scrape-preview');
    const previewTitle = document.getElementById('news-preview-title');
    const previewDate = document.getElementById('news-preview-date');
    const confirmNewsBtn = document.getElementById('confirm-add-news');

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
                    confirmNewsBtn.disabled = false;
                } else {
                    previewTitle.innerText = 'URL 정보를 가져오지 못했습니다.';
                }
            } catch (err) {
                previewTitle.innerText = '오류 발생: ' + err.message;
            }
        });
    }

    // 뉴스 추가 확인 버튼
    if (confirmNewsBtn) {
        confirmNewsBtn.onclick = async () => {
            if (!SCRAPED_NEWS_DATA || !CURRENT_NEWS_TICKER) return;
            const boardName = document.getElementById('board-select').value;
            try {
                const response = await fetch(
                    `/api/stock/news/add?board=${boardName}&ticker=${CURRENT_NEWS_TICKER}&title=${encodeURIComponent(SCRAPED_NEWS_DATA.title)}&date=${encodeURIComponent(SCRAPED_NEWS_DATA.date)}&url=${encodeURIComponent(SCRAPED_NEWS_DATA.url)}`,
                    { method: 'POST' }
                );
                if (response.ok) {
                    addLogEntry(`[API] 뉴스 추가 성공: ${SCRAPED_NEWS_DATA.title}`, 'success');
                    closeModal('add-news-modal');
                    await loadBoardData(boardName);
                    await fetchNews(CURRENT_NEWS_TICKER, fetchStockInfo, loadBoardData, globalLocalReportCounts);
                } else {
                    alert('뉴스 추가에 실패했습니다.');
                }
            } catch (err) {
                alert(`추가 중 오류 발생: ${err.message}`);
            }
        };
    }
}
