/**
 * @fileoverview 리포트 조회, 업로드, 삭제 서비스 모듈.
 * @module services/report_service
 */
import { addLogEntry } from '../ui/tabs.js';

/**
 * @typedef {Object} ReportInfo
 * @property {string} date - `YYYY.MM.DD` 형식의 날짜 문자열. 파싱 실패 시 빈 문자열.
 * @property {string} title - `[브로커명] 제목` 형식으로 가공된 리포트 제목.
 */

/**
 * @typedef {Object} ReportItem
 * @property {string} url - 리포트 파일에 접근할 수 있는 URL.
 * @property {string} filename - 원본 파일명.
 * @property {boolean} isLocal - 자동 수집된 로컬 리포트 여부.
 */

/**
 * 리포트 파일명에서 날짜와 제목을 파싱합니다.
 *
 * 파일명 패턴: `YYYYMMDD_[종목]_[브로커]_제목_ID.pdf`
 *
 * @param {string} filename - 파싱할 리포트 파일명.
 * @returns {ReportInfo} 파싱된 날짜와 제목.
 *
 * @example
 * parseReportInfo('20260320_[삼성전자]_[미래에셋]_실적분석_1081800.pdf');
 * // => { date: '2026.03.20', title: '[미래에셋] 실적분석' }
 */
export function parseReportInfo(filename) {
    const name = filename.replace('.pdf', '');
    const parts = name.split('_');

    let date = '';
    let title = filename;
    let broker = '';

    if (parts.length >= 4 && /^\d{8}$/.test(parts[0])) {
        const d = parts[0];
        date = `${d.substring(0, 4)}.${d.substring(4, 6)}.${d.substring(6, 8)}`;
        broker = parts[2].replace(/[\[\]]/g, '');

        const titleParts = parts.slice(3);
        if (titleParts.length > 1 && /^\d+$/.test(titleParts[titleParts.length - 1])) {
            title = titleParts.slice(0, -1).join('_');
        } else {
            title = titleParts.join('_');
        }

        if (broker) title = `[${broker}] ${title}`;
    }

    return { date, title };
}

/**
 * 특정 종목의 리포트 목록(수동 등록 + 자동 수집)을 조회하여 DOM에 렌더링합니다.
 *
 * 수동 등록 리포트와 로컬 수집 리포트를 병합하고, 파일명 기준 내림차순으로 정렬합니다.
 * 중복 파일은 파일명 기준으로 제거됩니다.
 *
 * @param {string} ticker - 조회할 종목 티커 심볼.
 * @param {string|null} name - 종목명. `null`인 경우 `fetchStockInfo`로 서버에서 조회.
 * @param {function(string): Promise<Object|null>} fetchStockInfo - 티커로 종목 정보를 조회하는 함수.
 * @param {function(string): Promise<void>} loadBoardData - 보드 데이터를 재로드하는 함수.
 * @returns {Promise<void>}
 */
export async function fetchReports(ticker, name = null, fetchStockInfo, loadBoardData) {
    const listEl = document.getElementById('report-list');
    if (!listEl) return;

    let stockRes = null;
    try {
        stockRes = await fetchStockInfo(ticker);
    } catch (e) { /* 무시 */ }

    let stockName = name || (stockRes ? stockRes.name : null);

    try {
        const manualReports = (stockRes && stockRes.reports) ? stockRes.reports : [];

        let localReports = [];
        if (stockName) {
            try {
                const localRes = await fetch(`/api/reports/local?name=${encodeURIComponent(stockName.normalize('NFC'))}`);
                localReports = await localRes.json();
            } catch (e) {
                console.error('Local reports fetch failed:', e);
            }
        }

        /** @type {ReportItem[]} */
        const allReports = [];

        manualReports.forEach(path => {
            const fname = path.split('/').pop().split('\\').pop();
            allReports.push({
                url: path.includes('data/pdf/') ? path.replace('data/pdf/', '/pdf/') : `/pdf/${fname}`,
                filename: fname,
                isLocal: false,
            });
        });

        localReports.forEach(report => {
            if (!allReports.find(r => r.filename === report.filename)) {
                allReports.push({ url: report.url, filename: report.filename, isLocal: true });
            }
        });

        if (allReports.length === 0) {
            listEl.innerHTML = '<div style="text-align: center; color: #6b7280; padding: 10px;">등록된 리포트가 없습니다.</div>';
            return;
        }

        allReports.sort((a, b) => b.filename.localeCompare(a.filename));

        listEl.innerHTML = '';
        allReports.forEach(report => {
            const { date, title } = parseReportInfo(report.filename);

            const wrapper = document.createElement('div');
            wrapper.className = 'report-item';
            wrapper.style.cssText = 'display:flex;justify-content:space-between;align-items:center;padding:12px 0;border-bottom:1px solid rgba(255,255,255,0.05);transition:background 0.2s;';

            const entry = document.createElement('a');
            entry.href = report.url;
            entry.target = '_blank';
            entry.className = 'report-link-alt';
            entry.style.cssText = 'flex:1;min-width:0;display:flex;justify-content:space-between;align-items:center;gap:15px;color:#e5e7eb;text-decoration:none;font-size:0.95rem;transition:color 0.2s;';

            const titleSpan = document.createElement('span');
            titleSpan.style.cssText = 'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;';
            titleSpan.innerText = title;

            const dateSpan = document.createElement('span');
            dateSpan.style.cssText = 'font-size:0.85rem;color:#6b7280;flex-shrink:0;';
            dateSpan.innerText = date || '';

            entry.appendChild(titleSpan);
            entry.appendChild(dateSpan);

            wrapper.onmouseover = () => { wrapper.style.background = 'rgba(239,68,68,0.03)'; entry.style.color = '#ef4444'; };
            wrapper.onmouseout = () => { wrapper.style.background = 'transparent'; entry.style.color = '#e5e7eb'; };

            const deleteBtn = document.createElement('button');
            deleteBtn.innerHTML = '&times;';
            deleteBtn.className = 'btn-delete-report';
            deleteBtn.title = '리포트 제거';
            deleteBtn.style.cssText = 'background:none;border:none;color:#6b7280;font-size:1.2rem;cursor:pointer;padding:0 5px;transition:color 0.2s;';
            deleteBtn.onmouseover = (e) => { e.stopPropagation(); deleteBtn.style.color = '#ef4444'; };
            deleteBtn.onmouseout = (e) => { e.stopPropagation(); deleteBtn.style.color = '#6b7280'; };
            deleteBtn.onclick = (e) => {
                e.preventDefault();
                e.stopPropagation();
                if (confirm(`'${report.filename}' 리포트 링크를 제거하시겠습니까?`)) {
                    deleteReport(ticker, report.url, fetchStockInfo, loadBoardData);
                }
            };

            wrapper.appendChild(entry);
            wrapper.appendChild(deleteBtn);
            listEl.appendChild(wrapper);
        });
    } catch (err) {
        listEl.innerHTML = `<div style="text-align:center;color:#ef4444;padding:10px;">로드 실패: ${err.message}</div>`;
    }
}

/**
 * PDF 리포트 파일을 서버에 업로드하고 UI를 갱신합니다.
 *
 * 업로드 성공 시 보드 데이터와 리포트 목록을 자동으로 새로고침합니다.
 *
 * @param {string} ticker - 업로드 대상 종목 티커.
 * @param {File} file - 업로드할 PDF 파일 객체. `.pdf` 확장자만 허용.
 * @param {function(string): Promise<Object|null>} fetchStockInfo - 종목 정보 조회 함수.
 * @param {function(string): Promise<void>} loadBoardData - 보드 데이터 재로드 함수.
 * @param {function(Object, string): Object|null} findStockByTicker - 트리에서 종목을 탐색하는 함수.
 * @returns {Promise<void>}
 */
export async function uploadReport(ticker, file, fetchStockInfo, loadBoardData, findStockByTicker) {
    if (!file.name.toLowerCase().endsWith('.pdf')) {
        alert('PDF 파일만 업로드 가능합니다.');
        return;
    }

    const boardName = document.getElementById('board-select').value;
    const formData = new FormData();
    formData.append('file', file);

    const listEl = document.getElementById('report-list');
    const originalContent = listEl.innerHTML;
    listEl.innerHTML = '<div class="loading-mini" style="text-align:center;color:#9ca3af;padding:10px;">업로드 중...</div>';

    try {
        const response = await fetch(`/api/stock/report/upload?board=${boardName}&ticker=${ticker}`, {
            method: 'POST',
            body: formData,
        });

        const result = await response.json();
        if (response.ok) {
            addLogEntry(`[API] 리포트 업로드 성공: ${file.name}`, 'success');
            await loadBoardData(boardName);
            const stock = findStockByTicker(window._currentBoardData, ticker);
            if (stock) {
                await fetchReports(ticker, null, fetchStockInfo, loadBoardData);
                const countEl = document.querySelector('.overview-stats .stat-item:nth-child(2) .count');
                if (countEl) countEl.innerText = stock.reports.length;
            }
        } else {
            alert(`업로드 실패: ${result.message}`);
            listEl.innerHTML = originalContent;
        }
    } catch (err) {
        alert(`업로드 중 오류 발생: ${err.message}`);
        listEl.innerHTML = originalContent;
    }
}

/**
 * 종목에 등록된 리포트 링크를 서버에서 삭제하고 UI를 갱신합니다.
 *
 * @param {string} ticker - 대상 종목 티커.
 * @param {string} reportPath - 삭제할 리포트의 URL 경로.
 * @param {function(string): Promise<Object|null>} fetchStockInfo - 종목 정보 조회 함수.
 * @param {function(string): Promise<void>} loadBoardData - 보드 데이터 재로드 함수.
 * @returns {Promise<void>}
 */
export async function deleteReport(ticker, reportPath, fetchStockInfo, loadBoardData) {
    const boardName = document.getElementById('board-select').value;
    try {
        const response = await fetch(
            `/api/stock/report/delete?board=${boardName}&ticker=${ticker}&report_path=${encodeURIComponent(reportPath)}`,
            { method: 'DELETE' }
        );

        if (response.ok) {
            addLogEntry(`[API] 리포트 제거 성공: ${reportPath.split('/').pop()}`, 'success');
            await loadBoardData(boardName);
            const stock = window._findStockByTicker(window._currentBoardData, ticker);
            if (stock) {
                await fetchReports(ticker, null, fetchStockInfo, loadBoardData);
                const countEl = document.querySelector('.overview-stats .stat-item:nth-child(2) .count');
                if (countEl) countEl.innerText = stock.reports.length;
            }
        } else {
            const result = await response.json();
            alert(`제거 실패: ${result.message}`);
        }
    } catch (err) {
        alert(`제거 중 오류 발생: ${err.message}`);
    }
}
