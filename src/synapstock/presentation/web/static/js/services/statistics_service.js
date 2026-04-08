/**
 * 수급 통계(Statistics) 서비스 모듈.
 * 백엔드 API와의 통신을 담당합니다.
 */
export const statisticsService = {
    /**
     * 특정일의 수급 순위 분석 데이터를 가져옵니다.
     * @param {string} date - YYYY-MM-DD 형식의 날짜
     * @param {string} market - KOSPI 또는 KOSDAQ
     * @param {string} subject - FOREIGN 또는 INSTITUTION
     */
    async getDailyRanking(date, market = 'KOSPI', subject = 'FOREIGN') {
        const url = `/api/statistics/daily-ranking?date=${date}&market=${market}&subject=${subject}`;
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error('Failed to fetch statistics data');
        }
        return await response.ok ? response.json() : null;
    },

    /**
     * 특정 날짜의 시장/주체별 4가지 조합 통계 데이터를 모두 가져옵니다.
     * @param {string} date - YYYY-MM-DD 형식의 날짜
     */
    async getDailySummary(date) {
        const url = `/api/statistics/daily-summary?date=${date}`;
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error('Failed to fetch daily summary');
        }
        return await response.json();
    },

    /**
     * 데이터가 존재하는 날짜 목록을 가져옵니다.
     * @param {string} market 
     * @param {string} subject 
     */
    async getAvailableDates(market = 'KOSPI', subject = 'FOREIGN') {
        const url = `/api/statistics/available-dates?market=${market}&subject=${subject}`;
        const response = await fetch(url);
        if (!response.ok) return [];
        return await response.json();
    },

    /**
     * 구글 드라이브로부터 최신 데이터를 동기화합니다.
     */
    async syncStatistics() {
        const response = await fetch('/api/statistics/sync', { method: 'POST' });
        if (!response.ok) throw new Error('Sync failed');
        return await response.json();
    }
};
