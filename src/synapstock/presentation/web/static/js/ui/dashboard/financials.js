/**
 * @fileoverview 재무(매출) 데이터 조회 및 사이드바 제어 모듈.
 * @module ui/dashboard/financials
 */

/**
 * 특정 기업의 분기별 재무 데이터를 조회하여 사이드바에 렌더링합니다.
 * @param {string} name 
 */
export async function fetchFinancials(name) {
    const listEl = document.getElementById('financial-list-sidebar');
    if (!listEl) return;
    try {
        const response = await fetch(`/api/stock/financials?name=${encodeURIComponent(name)}`);
        const data = await response.json();
        if (!data || !Array.isArray(data) || data.length === 0) {
            listEl.innerHTML = '<div style="text-align:center;color:#6b7280;padding:40px;">데이터가 없습니다.</div>';
            return;
        }
        listEl.innerHTML = '';
        data.forEach(item => {
            const entry = document.createElement('div');
            entry.style.cssText = 'display:flex;justify-content:space-between;padding:12px 0;border-bottom:1px solid rgba(255,255,255,0.05);';
            entry.innerHTML = `
                <span style="color:#9ca3af;font-weight:500;">${item.quarter}</span>
                <span style="color:#e5e7eb;font-weight:600;">${item.value.toLocaleString()}</span>
            `;
            listEl.appendChild(entry);
        });
    } catch (err) {
        listEl.innerHTML = `<div style="text-align:center;color:#ef4444;padding:20px;">로드 실패: ${err.message}</div>`;
    }
}

/**
 * 재무 사이드바 개폐 로직을 초기화합니다.
 */
export function initFinancialSidebar() {
    const sidebar = document.getElementById('financial-sidebar');
    const toggleBtn = document.getElementById('toggle-financial-sidebar');

    if (toggleBtn && sidebar) {
        toggleBtn.onclick = () => {
            sidebar.classList.toggle('open');
            toggleBtn.classList.toggle('sidebar-open');
        };
    }
}
