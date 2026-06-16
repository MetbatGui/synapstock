/**
 * @fileoverview DART 공시 목록 조회 모듈.
 * @module ui/dashboard/disclosure
 */

/**
 * 특정 종목의 DART 공시 목록을 조회하여 `#disclosure-list` 요소에 렌더링합니다.
 * @param {string} ticker 
 */
export async function fetchDisclosures(ticker) {
    const listEl = document.getElementById('disclosure-list');
    if (!listEl) return;
    try {
        const response = await fetch(`/api/disclosure/${ticker}`);
        const data = await response.json();
        if (!data || !Array.isArray(data) || data.length === 0) {
            listEl.innerHTML = '<div style="text-align:center;color:#6b7280;padding:20px;">최근 1년 이내 공시가 없습니다.</div>';
            return;
        }
        listEl.innerHTML = '';
        data.forEach(item => {
            const entry = document.createElement('div');
            entry.className = 'disclosure-item';
            entry.innerHTML = `
                <a href="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${item.rcpNo}"
                   target="_blank" class="disclosure-title" title="${item.title}">${item.title}</a>
                <span class="disclosure-date">${item.date}</span>
            `;
            listEl.appendChild(entry);
        });
    } catch (err) {
        listEl.innerHTML = `<div style="text-align:center;color:#ef4444;padding:20px;">로드 실패: ${err.message}</div>`;
    }
}
