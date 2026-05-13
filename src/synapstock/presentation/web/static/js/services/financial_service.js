/**
 * 재무 분석(Financial Analysis) 서비스 모듈.
 */
export const financialService = {
    /**
     * 사용 가능한 분기 목록을 가져옵니다.
     * @param {string} metric - REVENUE, OPERATING_PROFIT, NET_INCOME
     */
    async getQuarters(metric) {
        const response = await fetch(`/api/financials/quarters?metric=${metric}`);
        if (!response.ok) throw new Error('분기 목록을 불러오지 못했습니다.');
        return await response.json();
    },

    /**
     * 전년 동기 대비 실적 급증 종목(Top Growers)을 가져옵니다.
     * @param {string} metric - REVENUE, OPERATING_PROFIT, NET_INCOME
     * @param {string|null} target_quarter - YYYY.NQ 형식 (null이면 최신)
     * @param {number} topN - 추출 개수
     */
    async getTopGrowers(metric, target_quarter = null, topN = 500) {
        let url = `/api/financials/top-growers?metric=${metric}&top_n=${topN}`;
        if (target_quarter) {
            url += `&target_quarter=${target_quarter}`;
        }
        
        const response = await fetch(url);
        if (!response.ok) throw new Error('재무 데이터를 불러오는 데 실패했습니다.');
        return await response.json();
    },

    /**
     * N분기 연속 실적이 상승한 종목을 가져옵니다.
     */
    async getConsecutiveGrowers(metric, target_quarter = null, count = 3) {
        let url = `/api/financials/consecutive-growers?metric=${metric}&count=${count}`;
        if (target_quarter) {
            url += `&target_quarter=${target_quarter}`;
        }
        
        const response = await fetch(url);
        if (!response.ok) throw new Error('연속 성장주 데이터를 불러오지 못했습니다.');
        return await response.json();
    }
};
