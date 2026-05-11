from typing import List
from ...domain.financials.models import FinancialMetric, FinancialAnalysisItem, FinancialStatement
from ...domain.financials.repository import FinancialRepository

class FinancialService:
    """재무 분석 비즈니스 로직을 처리하는 서비스."""
    
    def __init__(self, repository: FinancialRepository):
        self.repository = repository

    def get_top_growers(
        self, 
        metric: FinancialMetric, 
        target_quarter: str | None = None, 
        top_n: int = 500,
        min_value: float = 1.0
    ) -> List[FinancialAnalysisItem]:
        """전년 동기 대비 등락률이 높은 상위 종목을 추출합니다.
        
        Args:
            metric: 분석할 재무 지표 (매출, 영업이익 등).
            target_quarter: 기준 분기 (None이면 최신 분기 자동 선택).
            top_n: 추출할 상위 종목 수.
            min_value: 노이즈 제거를 위한 최소 금액 기준 (단위: 백만 원).
        """
        
        # 1. 데이터 로드 및 기준 분기 결정
        if not target_quarter:
            target_quarter = self.repository.get_latest_quarter(metric)
            
        if not target_quarter:
            return []

        statements = self.repository.load_all(metric)
        prev_quarter = self._get_prev_year_quarter(target_quarter)
        
        if not prev_quarter:
            return []
        
        results = []
        for s in statements:
            curr_val = s.values.get(target_quarter)
            prev_val = s.values.get(prev_quarter)
            
            # 둘 중 하나라도 데이터가 없으면 제외
            if curr_val is None or prev_val is None:
                continue
                
            # 노이즈 필터링: 이전값과 현재값 모두 최소 기준치 미만이면 유의미한 변동으로 보기 어려움
            if abs(curr_val) < min_value and abs(prev_val) < min_value:
                continue
                
            # 2. 등락률 계산
            change_rate = self._calculate_change_rate(curr_val, prev_val)
            
            results.append(FinancialAnalysisItem(
                stock_name=s.stock_name,
                current_value=curr_val,
                prev_value=prev_val,
                change_rate=change_rate
            ))
            
        # 3. 정렬: 1순위 등락률 내림차순, 2순위 현재가 내림차순 (규모 우선)
        results.sort(key=lambda x: (x.change_rate, x.current_value), reverse=True)
        
        return results[:top_n]

    def _get_prev_year_quarter(self, quarter_str: str) -> str:
        """'2024.1Q' 형식에서 1년 전(4분기 전) 문자열을 반환합니다."""
        try:
            if not quarter_str or '.' not in quarter_str:
                return ""
            year_part, q_part = quarter_str.split('.')
            return f"{int(year_part) - 1}.{q_part}"
        except (ValueError, TypeError, IndexError):
            return ""

    def _calculate_change_rate(self, curr: float, prev: float) -> float:
        """등락률 계산 로직.
        
        - 일반 공식: (현재 - 이전) / abs(이전) * 100
        - 이를 통해 흑자 전환 시 100% 이상의 역동적인 수치 산출 가능
        """
        # 기저가 0인 경우 처리 (분모 0 방지)
        if prev == 0:
            if curr > 0: return 100.0
            if curr < 0: return -100.0
            return 0.0
            
        # 표준 등락률 공식 (음수 기저 효과 대응)
        rate = (curr - prev) / abs(prev) * 100.0
        
        return round(rate, 2)
