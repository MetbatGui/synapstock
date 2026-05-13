from typing import List
from ...domain.financials.models import FinancialMetric, FinancialAnalysisItem, FinancialStatement
from ...domain.financials.repository import FinancialRepository

class FinancialService:
    """재무 분석 비즈니스 로직을 처리하는 서비스."""
    
    def __init__(self, repository: FinancialRepository):
        self.repository = repository

    def get_available_quarters(self, metric: FinancialMetric) -> List[str]:
        """선택 가능한 모든 분기 리스트를 반환합니다."""
        return self.repository.get_all_quarters(metric)

    def get_top_growers(
        self, 
        metric: FinancialMetric, 
        target_quarter: str | None = None, 
        top_n: int = 500,
        min_value: float = 1.0
    ) -> List[FinancialAnalysisItem]:
        """직전 분기 대비 등락률이 높은 상위 종목을 추출합니다. (QoQ)"""
        
        # 1. 데이터 로드 및 기준 분기 결정
        if not target_quarter:
            target_quarter = self.repository.get_latest_quarter(metric)
            
        if not target_quarter:
            return []

        # 2. 비교 대상인 '직전 분기' 찾기
        prev_quarter = self._get_prev_quarter(target_quarter)
        
        # 화면에 표시할 최근 5개 분기 목록 (흐름 유지를 위해)
        quarters_to_show = self._get_recent_quarters(target_quarter, count=5)
        
        statements = self.repository.load_all(metric)
        
        results = []
        for s in statements:
            curr_val = s.values.get(target_quarter)
            # 신생 기업 제외: 현재 분기 데이터가 없으면 스킵
            if curr_val is None:
                continue
            
            # 동적 기저 분기 탐색 (직전 분기부터 과거로 4개 분기까지 뒤져서 데이터 있는 지점 찾기)
            search_range = self._get_recent_quarters(target_quarter, count=5)[:-1] 
            search_range.reverse() 
            
            actual_prev_val = None
            for q in search_range:
                val = s.values.get(q)
                if val is not None:
                    actual_prev_val = val
                    break
            
            if actual_prev_val is None:
                continue 
                
            # 3. 등락률 계산
            base_val = actual_prev_val
            if base_val == 0:
                change_rate = round(curr_val * 100.0, 2)
            else:
                change_rate = self._calculate_change_rate(curr_val, base_val)
            
            # 노이즈 필터링
            if abs(curr_val) < min_value and abs(base_val) < min_value:
                continue
            
            # 4. 히스토리 데이터 수집
            history = {q: s.values.get(q, 0.0) for q in quarters_to_show}
            
            results.append(FinancialAnalysisItem(
                stock_name=s.stock_name,
                current_value=curr_val,
                prev_value=actual_prev_val,
                change_rate=change_rate,
                history=history
            ))
            
        # 5. 정렬: 1순위 등락률 내림차순, 2순위 현재가 내림차순
        results.sort(key=lambda x: (x.change_rate, x.current_value), reverse=True)
        
        return results[:top_n]

    def get_consecutive_growers(
        self,
        metric: FinancialMetric,
        target_quarter: str | None = None,
        count: int = 3,
        min_value: float = 1.0
    ) -> List[FinancialAnalysisItem]:
        """지정된 분기부터 과거 N분기 동안 연속으로 실적이 상승한 종목을 추출합니다."""
        
        if not target_quarter:
            target_quarter = self.repository.get_latest_quarter(metric)
            
        if not target_quarter:
            return []

        # 필요한 분기 목록 (N분기 연속 상승이면 N+1개 데이터 필요)
        needed_count = count + 1
        quarters = self._get_recent_quarters(target_quarter, count=needed_count)
        
        statements = self.repository.load_all(metric)
        results = []
        
        for s in statements:
            # 해당 기간 데이터가 모두 있는지 확인
            vals = [s.values.get(q) for q in quarters]
            if any(v is None for v in vals):
                continue
            
            # 연속 상승 조건 체크 (Q[i] > Q[i-1])
            is_consecutive = True
            for i in range(1, len(vals)):
                if vals[i] <= vals[i-1]:
                    is_consecutive = False
                    break
            
            if is_consecutive:
                # 노이즈 필터링 (최소 실적 기준)
                if abs(vals[-1]) < min_value:
                    continue
                    
                # 등락률은 전체 기간(첫 분기 대비 마지막 분기)으로 계산
                change_rate = self._calculate_change_rate(vals[-1], vals[0])
                
                # 히스토리 데이터 (차트용)
                history = {q: s.values.get(q, 0.0) for q in quarters}
                
                results.append(FinancialAnalysisItem(
                    stock_name=s.stock_name,
                    current_value=vals[-1],
                    prev_value=vals[0],
                    change_rate=change_rate,
                    history=history
                ))
        
        # 최신 실적 규모 순으로 정렬
        results.sort(key=lambda x: x.current_value, reverse=True)
        return results

    def _get_prev_quarter(self, quarter_str: str) -> str:
        """'2024.1Q' 형식에서 직전 분기 문자열을 반환합니다."""
        try:
            year, q_str = quarter_str.split('.')
            year = int(year)
            q = int(q_str[0])
            
            p_y, p_q = (year, q-1) if q > 1 else (year-1, 4)
            return f"{p_y}.{p_q}Q"
        except Exception:
            return ""

    def _get_recent_quarters(self, start_quarter: str, count: int = 5) -> List[str]:
        """시작 분기부터 역순으로 지정된 개수만큼의 분기 리스트를 반환합니다. (오름차순 정렬됨)"""
        try:
            year, q_str = start_quarter.split('.')
            year = int(year)
            q_num = int(q_str[0])  # '4Q' -> 4
            
            quarters = []
            curr_year = year
            curr_q = q_num
            
            for _ in range(count):
                quarters.append(f"{curr_year}.{curr_q}Q")
                curr_q -= 1
                if curr_q < 1:
                    curr_q = 4
                    curr_year -= 1
            
            return sorted(quarters) # 시간 순서대로 정렬
        except Exception:
            return [start_quarter]

    def _calculate_change_rate(self, curr: float, prev: float) -> float:
        """등락률 계산 로직. (기저값이 0이 아님을 보장받고 호출됨)"""
        # 표준 등락률 공식 (음수 기저 효과 대응)
        rate = (curr - prev) / abs(prev) * 100.0
        return round(rate, 2)
