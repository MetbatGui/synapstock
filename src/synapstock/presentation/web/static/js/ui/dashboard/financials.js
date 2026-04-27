/**
 * @fileoverview 재무(매출) 데이터 조회 및 사이드바 제어 모듈.
 * @module ui/dashboard/financials
 */

let currentFinancialData = [];
let currentViewMode = 'list'; // 'list' or 'chart'
let financialChartInstance = null;

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
            currentFinancialData = [];
            listEl.innerHTML = '<div style="text-align:center;color:#6b7280;padding:40px;">데이터가 없습니다.</div>';
            if (financialChartInstance) {
                financialChartInstance.destroy();
                financialChartInstance = null;
            }
            return;
        }
        
        currentFinancialData = data;
        updateFinancialView();
    } catch (err) {
        currentFinancialData = [];
        listEl.innerHTML = `<div style="text-align:center;color:#ef4444;padding:20px;">로드 실패: ${err.message}</div>`;
    }
}

function updateFinancialView() {
    const sidebar = document.getElementById('financial-sidebar');
    const listEl = document.getElementById('financial-list-sidebar');
    const chartContainer = document.getElementById('financial-chart-container');
    
    if (!listEl || !chartContainer || !sidebar) return;

    if (currentViewMode === 'list') {
        sidebar.classList.remove('expanded');
        listEl.style.display = 'block';
        chartContainer.style.display = 'none';
        renderList();
    } else {
        sidebar.classList.add('expanded');
        listEl.style.display = 'none';
        chartContainer.style.display = 'block';
        renderChart();
    }

    // 트랜지션 후에 차트 크기를 다시 계산
    if (financialChartInstance) {
        setTimeout(() => {
            financialChartInstance.resize();
            financialChartInstance.update();
        }, 410);
    }
}

function renderList() {
    const listEl = document.getElementById('financial-list-sidebar');
    listEl.innerHTML = '';
    
    // 리스트는 최신 데이터가 위로 오도록 역순(reverse) 정렬
    const reversedData = [...currentFinancialData].reverse();
    
    reversedData.forEach(item => {
        const entry = document.createElement('div');
        entry.style.cssText = 'display:flex;justify-content:space-between;padding:12px 0;border-bottom:1px solid rgba(255,255,255,0.05);';
        entry.innerHTML = `
            <span style="color:#9ca3af;font-weight:500;">${item.quarter}</span>
            <span style="color:#e5e7eb;font-weight:600;">${item.value.toLocaleString()}</span>
        `;
        listEl.appendChild(entry);
    });
}

function renderChart() {
    const canvas = document.getElementById('financial-chart');
    if (!canvas) return;

    // 차트는 시간 흐름(과거->최신) 그대로 표시하되, 너무 많으면 보기 어려우므로 최근 30분기(약 7.5년)만 표시
    const displayData = currentFinancialData.slice(-30);

    const labels = displayData.map(d => d.quarter);
    const values = displayData.map(d => d.value);

    if (financialChartInstance) {
        financialChartInstance.data.labels = labels;
        financialChartInstance.data.datasets[0].data = values;
        financialChartInstance.update();
    } else {
        const ctx = canvas.getContext('2d');
        // 글로벌 Chart.js (CDN) 객체 사용
        financialChartInstance = new window.Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: '매출액 (억원)',
                    data: values,
                    backgroundColor: 'rgba(0, 210, 255, 0.6)',
                    borderColor: 'rgba(0, 210, 255, 1)',
                    borderWidth: 1,
                    borderRadius: 4,
                    hoverBackgroundColor: 'rgba(0, 210, 255, 0.9)'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: 'rgba(17, 24, 39, 0.95)',
                        titleColor: '#9ca3af',
                        bodyColor: '#e5e7eb',
                        borderColor: 'rgba(0, 210, 255, 0.3)',
                        borderWidth: 1,
                        padding: 12,
                        displayColors: false,
                        callbacks: {
                            label: function(context) {
                                const currentVal = context.raw;
                                const dataIndex = context.dataIndex;
                                // displayData는 최근 30개이므로, 전체 데이터에서의 실제 인덱스 계산
                                const displayDataSize = displayData.length;
                                const fullIndex = currentFinancialData.length - displayDataSize + dataIndex;
                                
                                let labels = [`매출액: ${currentVal.toLocaleString()} 억원`];
                                
                                // QoQ (직전 분기 대비)
                                if (fullIndex > 0) {
                                    const prevVal = currentFinancialData[fullIndex - 1].value;
                                    if (prevVal > 0) {
                                        const qoq = ((currentVal - prevVal) / prevVal) * 100;
                                        labels.push(`QoQ: ${qoq >= 0 ? '+' : ''}${qoq.toFixed(1)}%`);
                                    } else {
                                        labels.push(`QoQ: -`);
                                    }
                                } else {
                                    labels.push(`QoQ: -`);
                                }
                                
                                // YoY (전년 동기 대비 - 4분기 전)
                                if (fullIndex >= 4) {
                                    const yoyVal = currentFinancialData[fullIndex - 4].value;
                                    if (yoyVal > 0) {
                                        const yoy = ((currentVal - yoyVal) / yoyVal) * 100;
                                        labels.push(`YoY: ${yoy >= 0 ? '+' : ''}${yoy.toFixed(1)}%`);
                                    } else {
                                        labels.push(`YoY: -`);
                                    }
                                } else {
                                    labels.push(`YoY: -`);
                                }
                                
                                return labels;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { display: false, drawBorder: false },
                        ticks: { color: '#9ca3af', maxRotation: 45, minRotation: 45 }
                    },
                    y: {
                        grid: { color: 'rgba(255, 255, 255, 0.05)', drawBorder: false },
                        ticks: { color: '#9ca3af', callback: function(value) { return value.toLocaleString(); } }
                    }
                }
            }
        });
    }
}

/**
 * 재무 사이드바 개폐 및 토글 로직을 초기화합니다.
 */
export function initFinancialSidebar() {
    const sidebar = document.getElementById('financial-sidebar');
    const toggleBtn = document.getElementById('toggle-financial-sidebar');
    const viewToggleInput = document.getElementById('financial-view-toggle');

    if (toggleBtn && sidebar) {
        toggleBtn.onclick = () => {
            sidebar.classList.toggle('open');
            toggleBtn.classList.toggle('sidebar-open');
        };
    }

    if (viewToggleInput) {
        viewToggleInput.addEventListener('change', (e) => {
            currentViewMode = e.target.checked ? 'chart' : 'list';
            if (currentFinancialData.length > 0) {
                updateFinancialView();
            }
        });
    }
}
