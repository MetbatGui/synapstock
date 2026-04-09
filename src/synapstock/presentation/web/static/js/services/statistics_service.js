/**
 * 수급 통계(Statistics) 서비스 모듈.
 * 백엔드 API와의 통신을 담당하며 순위 데이터 조회, 날짜 목록 조회, 동기화 기능을 제공합니다.
 * 
 * @namespace
 */
export const statisticsService = {
    /**
     * 특정일의 특정 시장/주체에 대한 분석된 수급 순위 데이터를 가져옵니다.
     * @async
     * @param {string} date - YYYY-MM-DD 형식의 날짜
     * @param {string} [market='KOSPI'] - 시장 구분 (KOSPI 또는 KOSDAQ)
     * @param {string} [subject='FOREIGN'] - 수급 주체 (FOREIGN 또는 INSTITUTION)
     * @returns {Promise<Object|null>} 분석된 랭킹 데이터 객체 또는 null
     */
    async getDailyRanking(date, market = 'KOSPI', subject = 'FOREIGN') {
        const url = `/api/statistics/daily-ranking?date=${date}&market=${market}&subject=${subject}`;
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error('Failed to fetch statistics data');
        }
        return await response.json();
    },

    /**
     * 특정 날짜의 코스피/코스닥 및 외인/기관의 4가지 조합 통계 데이터를 종합하여 가져옵니다.
     * @async
     * @param {string} date - YYYY-MM-DD 형식의 날짜
     * @returns {Promise<Object>} 4분할 요약 통계 데이터 객체
     * @throws {Error} 네트워크 오류나 서버 응답 실패 시
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
     * 특정 월의 코스피/코스닥 및 외인/기관의 4가지 조합 월간 누적 통계 데이터를 종합하여 가져옵니다.
     * @async
     * @param {string} month - YYYY-MM 형식의 월
     * @returns {Promise<Object>} 4분할 월간 요약 통계 데이터 객체
     */
    async getMonthlySummary(month) {
        const url = `/api/statistics/monthly-summary?month=${month}`;
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error('Failed to fetch monthly summary');
        }
        return await response.json();
    },

    /**
     * 통계 데이터가 존재하는 시스템 내 가용 날짜 목록을 조회합니다.
     * @async
     * @param {string} [market='KOSPI'] - 기준 시장
     * @param {string} [subject='FOREIGN'] - 기준 주체
     * @returns {Promise<string[]>} YYYY-MM-DD 형식의 날짜 문자열 배열
     */
    async getAvailableDates(market = 'KOSPI', subject = 'FOREIGN') {
        const url = `/api/statistics/available-dates?market=${market}&subject=${subject}`;
        const response = await fetch(url);
        if (!response.ok) return [];
        return await response.json();
    },

    /**
     * 구글 드라이브로부터 최신 수급 엑셀 데이터를 가져와 시스템과 동기화하도록 요청합니다.
     * @async
     * @returns {Promise<Object>} 동기화 결과 상세 정보
     * @throws {Error} 동기화 프로세스 오류 발생 시
     */
    async syncStatistics() {
        const response = await fetch('/api/statistics/sync', { method: 'POST' });
        if (!response.ok) throw new Error('Sync failed');
        return await response.json();
    }
};
