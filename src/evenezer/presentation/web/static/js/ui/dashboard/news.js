/**
 * @fileoverview 뉴스 조회 및 관리 모듈.
 * @module ui/dashboard/news
 */
import { addLogEntry } from '../tabs.js';
import { openModal, closeModal } from '../mindmap/modals.js';

let CURRENT_NEWS_TICKER = '';
let SCRAPED_NEWS_DATA = null;

/**
 * 특정 종목의 뉴스 목록을 서버에서 조회하여 렌더링합니다.
 * @param {string} ticker 
 * @param {function} fetchStockInfo 
 * @param {function} loadBoardData 
 * @param {Object} globalLocalReportCounts 
 */
export async function fetchNews(ticker, fetchStockInfo, loadBoardData, globalLocalReportCounts, refresh = false) {
    const listEl = document.getElementById('news-list');
    if (!listEl) return;

    listEl.innerHTML = '<div style="text-align:center;color:#6b7280;padding:10px;">로딩 중...</div>';

    try {
        const stockData = await fetchStockInfo(ticker, refresh);
        if (!stockData || !stockData.news || stockData.news.length === 0) {
            listEl.innerHTML = '<div style="text-align:center;color:#6b7280;padding:20px;">등록된 뉴스가 없습니다.</div>';
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
            entry.innerHTML = `<i class="fas fa-newspaper" style="color:#facc15;flex-shrink:0;"></i> <span class="news-summary" title="${item.title}">${item.title}</span>`;

            const dateSpan = document.createElement('span');
            dateSpan.className = 'news-date';
            dateSpan.innerText = item.date;

            const deleteBtn = document.createElement('button');
            deleteBtn.innerHTML = '&times;';
            deleteBtn.className = 'btn-delete-news';
            deleteBtn.style.cssText = 'background:none;border:none;color:#6b7280;cursor:pointer;font-size:1.2rem;padding:0 5px;';
            deleteBtn.onclick = (e) => {
                e.preventDefault();
                e.stopPropagation();
                if (confirm('이 뉴스를 삭제하시겠습니까?')) {
                    deleteNews(ticker, item.url, fetchStockInfo, loadBoardData, globalLocalReportCounts);
                }
            };

            wrapper.appendChild(entry);
            wrapper.appendChild(dateSpan);
            wrapper.appendChild(deleteBtn);
            listEl.appendChild(wrapper);
        });
    } catch (err) {
        listEl.innerHTML = `<div style="text-align:center;color:#ef4444;padding:10px;">로드 실패: ${err.message}</div>`;
    }
}

/**
 * 뉴스를 삭제합니다.
 */
export async function deleteNews(ticker, url, fetchStockInfo, loadBoardData, globalLocalReportCounts) {
    const boardName = document.getElementById('board-select').value;
    try {
        const response = await fetch(`/api/stock/news/delete?board=${boardName}&ticker=${ticker}&url=${encodeURIComponent(url)}`, { method: 'DELETE' });
        if (response.ok) {
            addLogEntry('[API] 뉴스 제거 성공', 'success');
            await loadBoardData(boardName);
            await fetchNews(ticker, fetchStockInfo, loadBoardData, globalLocalReportCounts);
        }
    } catch (err) {
        alert(`삭제 중 오류 발생: ${err.message}`);
    }
}

/**
 * 뉴스 추가 모달을 표시합니다.
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
 * 뉴스 추가 이벤트(URL 스크래핑 등)를 초기화합니다.
 */
export function initNewsEvents(loadBoardData, fetchStockInfo, globalLocalReportCounts) {
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
                const response = await fetch(`/api/stock/news/add?board=${boardName}&ticker=${CURRENT_NEWS_TICKER}&title=${encodeURIComponent(SCRAPED_NEWS_DATA.title)}&date=${encodeURIComponent(SCRAPED_NEWS_DATA.date)}&url=${encodeURIComponent(SCRAPED_NEWS_DATA.url)}`, { method: 'POST' });
                if (response.ok) {
                    addLogEntry(`[API] 뉴스 추가 성공: ${SCRAPED_NEWS_DATA.title}`, 'success');
                    closeModal('add-news-modal');
                    await loadBoardData(boardName);
                    await fetchNews(CURRENT_NEWS_TICKER, fetchStockInfo, loadBoardData, globalLocalReportCounts);
                }
            } catch (err) {
                alert(`추가 중 오류 발생: ${err.message}`);
            }
        };
    }
}
