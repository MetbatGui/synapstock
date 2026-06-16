/**
 * @fileoverview 리포트(PDF) 조회 및 관리 모듈.
 * @module ui/dashboard/reports
 */
import { addLogEntry } from '../tabs.js';

export let CURRENT_UPLOAD_TICKER = '';

/**
 * 리포트 파일명에서 날짜와 제목 추출.
 */
function parseReportInfo(filename) {
    const name = filename.replace('.pdf', '');
    const parts = name.split('_');
    let date = "";
    let title = filename;
    let broker = "";

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
 * 리포트 목록 조회 및 렌더링.
 */
export async function fetchReports(ticker, name, fetchStockInfo, loadBoardData) {
    const listEl = document.getElementById('report-list');
    if (!listEl) return;

    try {
        const stockRes = await fetchStockInfo(ticker);
        const stockName = name || (stockRes ? stockRes.name : null);
        const manualReports = (stockRes && stockRes.reports) ? stockRes.reports : [];

        let localReports = [];
        if (stockName) {
            const localRes = await fetch(`/api/reports/local?name=${encodeURIComponent(stockName.normalize('NFC'))}`);
            localReports = await localRes.json();
        }

        const allReports = [];
        manualReports.forEach(path => {
            const fname = path.split('/').pop().split('\\').pop();
            allReports.push({ url: `/pdf/${fname}`, filename: fname, isLocal: false });
        });

        localReports.forEach(report => {
            if (!allReports.find(r => r.filename === report.filename)) {
                allReports.push({ url: report.url, filename: report.filename, isLocal: true });
            }
        });

        if (allReports.length === 0) {
            listEl.innerHTML = '<div style="text-align:center;color:#6b7280;padding:10px;">등록된 리포트가 없습니다.</div>';
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
            entry.style.cssText = 'flex:1;min-width:0;display:flex;justify-content:space-between;gap:15px;color:#e5e7eb;text-decoration:none;font-size:0.95rem;';
            entry.innerHTML = `<span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;">${title}</span><span style="font-size:0.85rem;color:#6b7280;">${date}</span>`;

            const deleteBtn = document.createElement('button');
            deleteBtn.innerHTML = '&times;';
            deleteBtn.style.cssText = 'background:none;border:none;color:#6b7280;cursor:pointer;font-size:1.2rem;padding:0 5px;';
            deleteBtn.onclick = (e) => {
                e.preventDefault();
                if (confirm(`'${report.filename}' 리포트를 제거하시겠습니까?`)) {
                    deleteReport(ticker, report.url, loadBoardData, fetchStockInfo);
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
 * 리포트 업로드 트리거.
 */
export function triggerReportUpload(ticker) {
    CURRENT_UPLOAD_TICKER = ticker;
    const input = document.getElementById('report-upload-input');
    if (input) {
        input.value = '';
        input.click();
    }
}

/**
 * 실제 업로드 처리.
 */
export async function uploadReport(ticker, file, fetchStockInfo, loadBoardData, findStockByTicker) {
    if (!file.name.toLowerCase().endsWith('.pdf')) { alert('PDF 파일만 가능합니다.'); return; }
    const boardName = document.getElementById('board-select').value;
    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch(`/api/stock/report/upload?board=${boardName}&ticker=${ticker}`, { method: 'POST', body: formData });
        if (response.ok) {
            addLogEntry(`[API] 리포트 업로드 성공: ${file.name}`, 'success');
            await loadBoardData(boardName);
            await fetchReports(ticker, null, fetchStockInfo, loadBoardData);
        }
    } catch (err) { alert(`업로드 오류: ${err.message}`); }
}

/**
 * 리포트 삭제.
 */
export async function deleteReport(ticker, reportPath, loadBoardData, fetchStockInfo) {
    const boardName = document.getElementById('board-select').value;
    try {
        const response = await fetch(`/api/stock/report/delete?board=${boardName}&ticker=${ticker}&report_path=${encodeURIComponent(reportPath)}`, { method: 'DELETE' });
        if (response.ok) {
            addLogEntry(`[API] 리포트 제거 성공`, 'success');
            await loadBoardData(boardName);
            await fetchReports(ticker, null, fetchStockInfo, loadBoardData);
        }
    } catch (err) { alert(`삭제 오류: ${err.message}`); }
}
