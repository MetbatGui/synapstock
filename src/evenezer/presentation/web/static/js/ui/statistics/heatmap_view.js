/**
 * @fileoverview KRX 테마 증시 히트맵 클라이언트 렌더러 모듈
 * @module ui/statistics/heatmap_view
 */

export const heatmapView = {
    _timerId: null,

    /**
     * 테마 히트맵 뷰 초기화 및 렌더링
     * @param {HTMLElement} container - 렌더링할 대상 부모 컨테이너
     */
    async init(container) {
        // 1. 화면 뼈대 및 로딩바 구성
        container.innerHTML = `
            <div class="stats-card animate-fade-in" style="display:flex; flex-direction:column; height: calc(100vh - 150px); min-height: 750px;">
                <div class="stats-card-header" style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 20px;">
                    <div style="display:flex; flex-direction:column; gap:5px;">
                        <h2 style="color: #00d2ff !important; margin: 0; font-size: 1.5rem;">📈 테마 증시 히트맵 (실시간 KRX)</h2>
                        <p style="color: #9ca3af; font-size: 0.85rem; margin: 0;">각 영역의 크기는 시가총액(조 원), 색상은 당일 등락률(%)을 나타냅니다. (종목 노드를 클릭하면 상세 대시보드로 이동합니다)</p>
                    </div>
                    <!-- 우측 상단 갱신 버튼 및 캐시 만료 연동 타이머 -->
                    <div style="display:flex; align-items:center; gap:12px;">
                        <span id="heatmap-timer" style="color: #9ca3af; font-size: 0.85rem; font-family: monospace; background: rgba(255,255,255,0.05); padding: 5px 10px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.08); display:none;">
                            다음 갱신까지 --:--
                        </span>
                        <button id="heatmap-refresh-btn" class="financial-opt-btn" style="background: rgba(0,210,255,0.1); color: #00d2ff; border: 1px solid rgba(0,210,255,0.2); font-size: 0.85rem; padding: 6px 14px; display:flex; align-items:center; gap:6px; border-radius: 8px; font-weight: 600;">
                            <i class="fas fa-sync-alt" id="refresh-icon"></i> 실시간 갱신
                        </button>
                    </div>
                </div>
                
                <div id="heatmap-content-wrapper" style="flex:1; position:relative; display:flex; justify-content:center; align-items:center; height: 100%; min-height: 600px; background: rgba(10,14,20,0.4); border-radius: 16px; border: 1px solid rgba(255,255,255,0.05); overflow:hidden;">
                    <div id="heatmap-shimmer" class="loading-shimmer" style="position:absolute; width:100%; height:100%; display:flex; flex-direction:column; justify-content:center; align-items:center; gap:15px; background: rgba(10,14,20,0.85); z-index:10;">
                        <div class="spinner" style="width: 50px; height: 50px; border: 4px solid rgba(0,210,255,0.1); border-top-color: #00d2ff; border-radius: 50%; animation: spin 1s linear infinite;"></div>
                        <span style="color:#00d2ff; font-weight:600; font-size:1.1rem; letter-spacing: 0.5px;">KRX 실시간 시세 데이터 조율 중...</span>
                    </div>
                    <div id="plotly-heatmap-canvas" style="width:100%; height:100%; min-height: 600px;"></div>
                </div>
            </div>
            
            <style>
                @keyframes spin {
                    to { transform: rotate(360deg); }
                }
                .financial-opt-btn {
                    background: transparent;
                    border: none;
                    color: #9ca3af;
                    padding: 8px 16px;
                    border-radius: 8px;
                    cursor: pointer;
                    font-weight: 600;
                    transition: 0.25s ease;
                }
                .financial-opt-btn:hover {
                    color: #f3f4f6;
                    background: rgba(255,255,255,0.02);
                }
                .financial-opt-btn.active {
                    background: linear-gradient(135deg, #00d2ff 0%, #9d50bb 100%);
                    color: #ffffff;
                    box-shadow: 0 0 12px rgba(0, 210, 255, 0.3);
                }
            </style>
        `;

        // 2. 최초 렌더링 실행 (종목 포함 뷰로 영구 고정)
        await this.fetchAndRender(true);

        // 3. 수동 갱신 버튼 이벤트 바인딩
        const refreshBtn = document.getElementById('heatmap-refresh-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', async () => {
                await this.fetchAndRender(true, true);
            });
        }
    },

    /**
     * API 통신 및 Plotly 그리기 수행
     * @param {boolean} showStocks - 종목 상세 노출 여부
     * @param {boolean} forceRefresh - 캐시 강제 무효화 여부
     */
    async fetchAndRender(showStocks, forceRefresh = false) {
        const shimmer = document.getElementById('heatmap-shimmer');
        const canvas = document.getElementById('plotly-heatmap-canvas');
        const refreshIcon = document.getElementById('refresh-icon');
        const refreshBtn = document.getElementById('heatmap-refresh-btn');
        
        // 기존 실행 중인 타이머가 있다면 즉각 정리
        if (this._timerId) {
            clearInterval(this._timerId);
            this._timerId = null;
        }

        if (shimmer) shimmer.style.display = 'flex';
        
        // UI 로딩 피드백 (회전 애니메이션 및 비활성화)
        if (refreshIcon) {
            refreshIcon.classList.add('fa-spin');
        }
        if (refreshBtn) {
            refreshBtn.disabled = true;
            refreshBtn.style.opacity = '0.6';
        }
        
        try {
            // 1. API 데이터 Fetch (강제 갱신 쿼리 매핑)
            const url = `/api/heatmap/data?show_categories=true&show_stocks=true${forceRefresh ? '&force_refresh=true' : ''}`;
            const response = await fetch(url);
            if (!response.ok) throw new Error(`HTTP Error ${response.status}`);
            const data = await response.json();
            
            // 클릭 바인딩용 전역 캐시 저장
            window._heatmapRawTickers = data.tickers || [];

            // 2. Plotly.js 옵션 튜닝
            const trace = {
                type: 'treemap',
                ids: data.ids,
                labels: data.labels,
                parents: data.parents,
                values: data.values,
                branchvalues: 'total',
                maxdepth: 2,
                
                // 등락률에 따른 색상 매핑
                marker: {
                    colors: data.colors,
                    colorscale: [
                        [0.0, 'blue'],
                        [0.5, '#444444'],
                        [1.0, 'red']
                    ],
                    cmin: -15.0,
                    cmax: 15.0,
                    showscale: true,
                    colorbar: {
                        title: '등락률 (%)',
                        thickness: 15,
                        len: 0.8,
                        ypad: 30,
                        tickfont: { color: '#9ca3af', family: 'Inter' }
                    },
                    line: { width: 1.5, color: '#0a0e14' }
                },
                
                customdata: data.colors,
                hovertemplate: '<b>%{label}</b><br>시가총액: %{value:.2f}조 원<br>등락률: %{customdata:.2f}%<extra></extra>',
                
                textinfo: 'label+value+percent entry',
                texttemplate: '<b>%{label}</b><br>%{value:.2f}조<br>%{customdata:+.2f}%',
                textposition: 'middle center',
                
                textfont: {
                    family: 'Inter, sans-serif',
                    size: 13,
                    color: '#ffffff'
                },
                
                pathbar: {
                    visible: true,
                    thickness: 25,
                    font: { family: 'Inter', size: 12, color: '#00d2ff' }
                }
            };
            
            const layout = {
                margin: { l: 5, r: 5, t: 30, b: 5 },
                paper_bgcolor: 'rgba(0,0,0,0)',
                plot_bgcolor: 'rgba(0,0,0,0)',
                font: { family: 'Inter, sans-serif', color: '#f3f4f6' }
            };
            
            const config = {
                responsive: true,
                displayModeBar: false
            };
            
            // 3. Plotly 렌더링 실행
            if (window.Plotly) {
                await window.Plotly.newPlot(canvas, [trace], layout, config);
                
                // 4. 클릭 이벤트 바인딩
                canvas.on('plotly_click', (eventData) => {
                    if (eventData && eventData.points && eventData.points[0]) {
                        const pt = eventData.points[0];
                        const pointIndex = pt.pointIndex;
                        
                        if (pointIndex !== undefined && window._heatmapRawTickers) {
                            const ticker = window._heatmapRawTickers[pointIndex];
                            const name = pt.label;
                            
                            if (ticker && ticker !== 'TBD' && ticker !== 'none' && ticker !== '') {
                                if (window._jumpToStock) {
                                    window._jumpToStock(ticker, name);
                                }
                            }
                        }
                    }
                });
            } else {
                throw new Error("Plotly.js 라이브러리가 로드되지 않았습니다.");
            }
            
            // 5. 타이머 기동 (expired_at 연동)
            if (data.expired_at) {
                const timerSpan = document.getElementById('heatmap-timer');
                if (timerSpan) {
                    timerSpan.style.display = 'inline-block';
                    this.startCountdown(data.expired_at, timerSpan);
                }
            }
            
        } catch (err) {
            console.error('Heatmap load failed:', err);
            canvas.innerHTML = `
                <div style="color:#ef4444; padding:20px; text-align:center; display:flex; flex-direction:column; gap:10px; align-items:center;">
                    <i class="fas fa-exclamation-triangle" style="font-size: 2.5rem;"></i>
                    <strong style="font-size:1.1rem;">히트맵을 불러오는 데 실패했습니다.</strong>
                    <span style="color:#9ca3af; font-size:0.9rem;">${err.message}</span>
                </div>
            `;
        } finally {
            if (shimmer) shimmer.style.display = 'none';
            if (refreshIcon) {
                refreshIcon.classList.remove('fa-spin');
            }
            if (refreshBtn) {
                refreshBtn.disabled = false;
                refreshBtn.style.opacity = '1';
            }
        }
    },

    /**
     * 캐시 만료 예정 시간을 토대로 카운트다운 타이머를 실행합니다.
     * @param {string} expiredAtStr - 캐시 만료 시각 (ISO 8601 형식)
     * @param {HTMLElement} timerSpan - 렌더링 영역
     */
    startCountdown(expiredAtStr, timerSpan) {
        const expiredAt = new Date(expiredAtStr);
        
        const updateTimer = () => {
            const now = new Date();
            const diffMs = expiredAt - now;
            
            if (diffMs <= 0) {
                clearInterval(this._timerId);
                this._timerId = null;
                timerSpan.textContent = '다음 갱신까지 00:00';
                // 00:00 도달 시 자동으로 캐시 데이터 신규 갱신
                this.fetchAndRender(true);
                return;
            }
            
            const totalSec = Math.floor(diffMs / 1000);
            const minutes = Math.floor(totalSec / 60);
            const seconds = totalSec % 60;
            
            const mm = String(minutes).padStart(2, '0');
            const ss = String(seconds).padStart(2, '0');
            
            timerSpan.textContent = `다음 갱신까지 ${mm}:${ss}`;
        };
        
        updateTimer();
        this._timerId = setInterval(updateTimer, 1000);
    }
};
