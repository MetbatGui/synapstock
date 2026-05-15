from ...domain.financials.models import FinancialAnalysisItem, FinancialMetric
from ...domain.financials.repository import FinancialRepository


class FinancialService:
    """재무 분석 비즈니스 로직을 처리하는 서비스."""

    def __init__(self, repository: FinancialRepository):
        self.repository = repository
        self._cache = {}  # {key: result_dict}

    def get_available_quarters(self, metric: FinancialMetric) -> list[str]:
        """선택 가능한 모든 분기 리스트를 반환합니다."""
        return self.repository.get_all_quarters(metric)

    def get_top_growers(
        self, metric: FinancialMetric, target_quarter: str | None = None, top_n: int = 500, min_value: float = 1.0
    ) -> dict:
        """직전 분기 대비 등락률이 높은 상위 종목을 추출합니다. (QoQ)
        일반 성장과 흑자 전환 결과를 동시에 반환하며 캐싱을 지원합니다.
        """
        if not target_quarter:
            target_quarter = self.repository.get_latest_quarter(metric)
        if not target_quarter:
            return {"normal": [], "turnaround": []}

        cache_key = f"top_{metric}_{target_quarter}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        quarters_to_show = self._get_recent_quarters(target_quarter, count=5)
        statements = self.repository.load_all(metric)

        normal_results = []
        turnaround_results = []

        for s in statements:
            curr_val = s.values.get(target_quarter)
            if curr_val is None:
                continue

            search_range = self._get_recent_quarters(target_quarter, count=6)[:-1]
            search_range.reverse()
            actual_prev_val = None
            pre_prev_val = None
            found_prev = False
            for q in search_range:
                val = s.values.get(q)
                if val is not None:
                    if not found_prev:
                        actual_prev_val = val
                        found_prev = True
                    else:
                        pre_prev_val = val
                        break

            if actual_prev_val is None:
                continue

            base_val = actual_prev_val
            change_rate = (
                self._calculate_change_rate(curr_val, base_val) if base_val != 0 else round(curr_val * 100.0, 2)
            )

            if abs(curr_val) < min_value and abs(base_val) < min_value:
                continue
            if curr_val < 0:
                continue

            history = {q: s.values.get(q, 0.0) for q in quarters_to_show}
            item = FinancialAnalysisItem(
                stock_name=s.stock_name,
                current_value=curr_val,
                prev_value=actual_prev_val,
                pre_prev_value=pre_prev_val,
                change_rate=change_rate,
                history=history,
            )

            if base_val <= 0 and curr_val > 0:
                turnaround_results.append(item)
            elif base_val > 0:
                normal_results.append(item)

        normal_results.sort(key=lambda x: (x.change_rate, x.current_value), reverse=True)
        turnaround_results.sort(key=lambda x: (x.change_rate, x.current_value), reverse=True)

        result = {"normal": normal_results[:top_n], "turnaround": turnaround_results[:top_n]}
        self._cache[cache_key] = result
        return result

    def get_consecutive_growers(
        self, metric: FinancialMetric, target_quarter: str | None = None, count: int = 3, min_value: float = 1.0
    ) -> dict:
        """지정한 분기부터 과거 N분기 동안 연속으로 실적이 상승한 종목을 추출합니다.
        일반 성장과 흑자 전환 결과를 동시에 반환하며 캐싱을 지원합니다.
        """
        if not target_quarter:
            target_quarter = self.repository.get_latest_quarter(metric)
        if not target_quarter:
            return {"normal": [], "turnaround": []}

        cache_key = f"cons_{metric}_{target_quarter}_{count}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        needed_count = count + 2
        quarters = self._get_recent_quarters(target_quarter, count=needed_count)
        statements = self.repository.load_all(metric)

        normal_results = []
        turnaround_results = []

        for s in statements:
            # 해당 기간 데이터가 모두 있는지 확인
            vals_with_none = [s.values.get(q) for q in quarters]
            if any(v is None for v in vals_with_none):
                continue

            # 타입 체커를 위한 명시적 타입 변환 (None이 없음을 확인한 후)
            vals: list[float] = [v for v in vals_with_none if v is not None]

            is_consecutive = True
            for i in range(2, len(vals)):
                if vals[i] <= vals[i - 1]:
                    is_consecutive = False
                    break

            if is_consecutive:
                if any(v < 0 for v in vals[2:]):
                    continue
                if abs(vals[-1]) < min_value:
                    continue

                change_rate = self._calculate_change_rate(vals[-1], vals[1])
                history = {q: s.values.get(q, 0.0) for q in quarters}

                item = FinancialAnalysisItem(
                    stock_name=s.stock_name,
                    current_value=vals[-1],
                    prev_value=vals[1],
                    pre_prev_value=vals[0],
                    change_rate=change_rate,
                    history=history,
                )

                if vals[1] <= 0 and vals[-1] > 0:
                    turnaround_results.append(item)
                elif vals[1] > 0:
                    normal_results.append(item)

        # 최신 실적 규모 순으로 정렬
        normal_results.sort(key=lambda x: x.current_value, reverse=True)
        turnaround_results.sort(key=lambda x: x.current_value, reverse=True)

        result = {"normal": normal_results[:500], "turnaround": turnaround_results[:500]}
        self._cache[cache_key] = result
        return result

    def _get_prev_quarter(self, quarter_str: str) -> str:
        """'2024.1Q' 형식에서 직전 분기 문자열을 반환합니다."""
        try:
            year, q_str = quarter_str.split(".")
            year = int(year)
            q = int(q_str[0])

            p_y, p_q = (year, q - 1) if q > 1 else (year - 1, 4)
            return f"{p_y}.{p_q}Q"
        except Exception:
            return ""

    def _get_recent_quarters(self, start_quarter: str, count: int = 5) -> list[str]:
        """시작 분기부터 역순으로 지정된 개수만큼의 분기 리스트를 반환합니다. (오름차순 정렬됨)"""
        try:
            year, q_str = start_quarter.split(".")
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

            return sorted(quarters)  # 시간 순서대로 정렬
        except Exception:
            return [start_quarter]

    def _calculate_change_rate(self, curr: float, prev: float) -> float:
        """등락률 계산 로직. (기저값이 0이 아님을 보장받고 호출됨)"""
        # 표준 등락률 공식 (음수 기저 효과 대응)
        rate = (curr - prev) / abs(prev) * 100.0
        return round(rate, 2)
