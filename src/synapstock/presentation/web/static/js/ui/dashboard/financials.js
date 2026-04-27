/**
 * @fileoverview 재무(매출) 데이터 조회 및 사이드바 제어 모듈.
 * @module ui/dashboard/financials
 */

let currentFinancialData = [];
let currentViewMode = 'list'; // 'list' or 'chart'
let currentMetric = '매출액';
let currentPeriod = '분기별';
let currentStockName = '';
let financialChartInstance = null;

/**
 * 특정 기업의 재무 데이터를 조회하여 사이드바에 렌더링합니다.
 * @param {string} name 
 */
export async function fetchFinancials(name) {
    if (!name) return;
    currentStockName = name;
    
    const listEl = document.getElementById('financial-list-sidebar');
    if (!listEl) return;
    
    updateHeaderUI();

    try {
        const response = await fetch(`/api/stock/financials?name=${encodeURIComponent(name)}&metric=${encodeURIComponent(currentMetric)}&period=${encodeURIComponent(currentPeriod)}`);
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

function updateHeaderUI() {
    const titleEl = document.getElementById('financial-title');
    if (titleEl) {
        const periodText = currentPeriod === '분기별' ? '분기' : '연간';
        titleEl.innerHTML = `💰 ${periodText} ${currentMetric} 현황 <span style="font-size: 0.8rem; color: #9ca3af; font-weight: normal; margin-left: 10px;">(단위: 억원)</span>`;
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
        const isNegative = item.value !== null && item.value < 0;
        const valueColor = isNegative ? '#e26a6a' : (item.value === null ? '#6b7280' : '#e5e7eb');
        const displayValue = item.value === null ? '-' : item.value.toLocaleString();
        
        const entry = document.createElement('div');
        entry.style.cssText = 'display:flex;justify-content:space-between;padding:12px 0;border-bottom:1px solid rgba(255,255,255,0.05);';
        entry.innerHTML = `
            <span style="color:#9ca3af;font-weight:500;">${item.quarter}</span>
            <span style="color:${valueColor};font-weight:600;">${displayValue}</span>
        `;
        listEl.appendChild(entry);
    });
}

function renderChart() {
    const canvas = document.getElementById('financial-chart');
    if (!canvas) return;

    // 차트는 시간 흐름(과거->최신) 그대로 표시하되, 최근 30개만 표시
    const displayData = currentFinancialData.slice(-30);

    const labels = displayData.map(d => d.quarter);
    
    // 데이터 부재 시 처리 로직: 이전의 유효한 값을 높이로 사용
    let lastValidValue = 0;
    const values = [];
    const missingFlags = [];

    displayData.forEach(d => {
        if (d.value === null) {
            values.push(lastValidValue);
            missingFlags.push(true);
        } else {
            values.push(d.value);
            missingFlags.push(false);
            lastValidValue = d.value;
        }
    });

    // 음수 값은 적색, 양수 값은 파란색, 데이터 부재는 회색 적용
    const backgroundColors = values.map((v, i) => {
        if (missingFlags[i]) return 'rgba(107, 114, 128, 0.5)'; // 회색
        return v < 0 ? 'rgba(226, 106, 106, 0.7)' : 'rgba(0, 210, 255, 0.6)';
    });
    const borderColors = values.map((v, i) => {
        if (missingFlags[i]) return 'rgba(107, 114, 128, 0.8)';
        return v < 0 ? 'rgba(226, 106, 106, 1)' : 'rgba(0, 210, 255, 1)';
    });

    if (financialChartInstance) {
        financialChartInstance.data.labels = labels;
        financialChartInstance.data.datasets[0].label = `${currentMetric} (억원)`;
        financialChartInstance.data.datasets[0].data = values;
        financialChartInstance.data.datasets[0].backgroundColor = backgroundColors;
        financialChartInstance.data.datasets[0].borderColor = borderColors;
        financialChartInstance.update();
    } else {
        const ctx = canvas.getContext('2d');
        // 글로벌 Chart.js (CDN) 객체 사용
        financialChartInstance = new window.Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: `${currentMetric} (억원)`,
                    data: values,
                    backgroundColor: backgroundColors,
                    borderColor: borderColors,
                    borderWidth: 1,
                    borderRadius: 4,
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
                                const dataIndex = context.dataIndex;
                                const displayDataSize = displayData.length;
                                const fullIndex = currentFinancialData.length - displayDataSize + dataIndex;
                                const originalData = currentFinancialData[fullIndex];
                                
                                if (originalData.value === null) {
                                    return ['데이터 부재', '(이전 수치 기준 표시)'];
                                }

                                const currentVal = originalData.value;
                                let labels = [`${currentMetric}: ${currentVal.toLocaleString()} 억원`];
                                
                                const periodLabel = currentPeriod === '분기별' ? 'QoQ' : '증감';
                                
                                // 직전 대비 (QoQ / 이전 연도)
                                if (fullIndex > 0) {
                                    const prevData = currentFinancialData[fullIndex - 1];
                                    if (prevData && prevData.value !== null && prevData.value > 0) {
                                        const diff = ((currentVal - prevData.value) / prevData.value) * 100;
                                        labels.push(`${periodLabel}: ${diff >= 0 ? '+' : ''}${diff.toFixed(1)}%`);
                                    }
                                }
                                
                                // YoY (분기별인 경우에만 1년 전 동일 분기 계산)
                                if (currentPeriod === '분기별' && fullIndex >= 4) {
                                    const yoyData = currentFinancialData[fullIndex - 4];
                                    if (yoyData && yoyData.value !== null && yoyData.value > 0) {
                                        const yoy = ((currentVal - yoyData.value) / yoyData.value) * 100;
                                        labels.push(`YoY: ${yoy >= 0 ? '+' : ''}${yoy.toFixed(1)}%`);
                                    }
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
    const metricBtns = document.querySelectorAll('.financial-opt-btn');
    const periodSelect = document.getElementById('financial-period-select');

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

    if (metricBtns) {
        metricBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                metricBtns.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                currentMetric = btn.getAttribute('data-metric');
                if (currentStockName) fetchFinancials(currentStockName);
            });
        });
    }

    if (periodSelect) {
        periodSelect.addEventListener('change', (e) => {
            currentPeriod = e.target.value;
            if (currentStockName) fetchFinancials(currentStockName);
        });
    }
}
