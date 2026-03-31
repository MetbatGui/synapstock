/**
 * @fileoverview 뉴스 조회 및 삭제 서비스 모듈.
 * @module services/news_service
 */
import { addLogEntry } from '../ui/tabs.js';

/**
 * @typedef {Object} NewsItem
 * @property {string} url - 뉴스 기사 URL.
 * @property {string} title - 뉴스 제목.
 * @property {string} date - `YYYY-MM-DD` 형식의 기사 날짜.
 */

/**
 * 특정 종목의 뉴스 목록을 서버에서 조회하여 DOM에 렌더링합니다.
 *
 * `fetchStockInfo`를 통해 종목 데이터를 조회한 뒤, `news` 배열을 순회하며
 * 삭제 버튼이 포함된 뉴스 아이템을 렌더링합니다.
 *
 * @param {string} ticker - 조회할 종목 티커 심볼.
 * @param {function(string): Promise<Object|null>} fetchStockInfo - 티커로 종목 정보를 조회하는 함수.
 * @param {function(string): Promise<void>} loadBoardData - 보드 데이터를 재로드하는 함수.
 * @param {Object<string, number>} globalLocalReportCounts - 종목명을 키로 하는 로컬 리포트 수량 맵.
 * @returns {Promise<void>}
 */
export async function fetchNews(ticker, fetchStockInfo, loadBoardData, globalLocalReportCounts) {
    const listEl = document.getElementById('news-list');
    if (!listEl) return;

    listEl.innerHTML = '<div style="text-align:center;color:#6b7280;padding:10px;">로딩 중...</div>';

    try {
        const stockData = await fetchStockInfo(ticker);
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
 * 종목에 등록된 뉴스를 서버에서 삭제하고 뉴스 목록을 새로고침합니다.
 *
 * @param {string} ticker - 대상 종목 티커 심볼.
 * @param {string} url - 삭제할 뉴스 기사 URL.
 * @param {function(string): Promise<Object|null>} fetchStockInfo - 종목 정보 조회 함수.
 * @param {function(string): Promise<void>} loadBoardData - 보드 데이터 재로드 함수.
 * @param {Object<string, number>} globalLocalReportCounts - 종목명을 키로 하는 로컬 리포트 수량 맵.
 * @returns {Promise<void>}
 */
export async function deleteNews(ticker, url, fetchStockInfo, loadBoardData, globalLocalReportCounts) {
    const boardName = document.getElementById('board-select').value;
    try {
        const response = await fetch(
            `/api/stock/news/delete?board=${boardName}&ticker=${ticker}&url=${encodeURIComponent(url)}`,
            { method: 'DELETE' }
        );
        if (response.ok) {
            addLogEntry('[API] 뉴스 제거 성공', 'success');
            await loadBoardData(boardName);
            await fetchNews(ticker, fetchStockInfo, loadBoardData, globalLocalReportCounts);
        }
    } catch (err) {
        alert(`삭제 중 오류 발생: ${err.message}`);
    }
}
