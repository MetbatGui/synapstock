import json
from pathlib import Path
from typing import Optional, List
from synapstock.domain.statistics.models import DailyMarketRanking, MarketType, SupplySubject

class LocalStatisticsRepository:
    """통계 데이터를 로컬 JSON 파일로 관리하는 저장소."""

    def __init__(self, data_root: str = "data/statistics"):
        self.root = Path(data_root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save_daily_ranking(self, ranking: DailyMarketRanking):
        """일별 순위를 저장한다."""
        # 파일명 형식: 2026-04-07_KOSPI_FOREIGN.json
        market_val = ranking.market.value if hasattr(ranking.market, 'value') else str(ranking.market)
        subject_val = ranking.subject.value if hasattr(ranking.subject, 'value') else str(ranking.subject)
        filename = f"{ranking.date}_{market_val}_{subject_val}.json"
        path = self.root / filename
        with open(path, "w", encoding="utf-8") as f:
            f.write(ranking.model_dump_json(indent=2))

    def load_ranking(
        self, 
        date: str, 
        market: MarketType, 
        subject: SupplySubject
    ) -> Optional[DailyMarketRanking]:
        """특정 날짜의 순위를 불러온다."""
        market_val = market.value if hasattr(market, 'value') else str(market)
        subject_val = subject.value if hasattr(subject, 'value') else str(subject)
        
        # 1. 정규 형식 시도 (*_KOSPI_FOREIGN.json)
        filename = f"{date}_{market_val}_{subject_val}.json"
        path = self.root / filename
        
        # 2. 존재하지 않으면 유연한 검색 시도
        if not path.exists():
            pattern = f"{date}*{market_val}*{subject_val}*.json"
            files = list(self.root.glob(pattern))
            if not files:
                return None
            path = files[0]
            
        with open(path, "r", encoding="utf-8") as f:
            return DailyMarketRanking.model_validate_json(f.read())

    def list_available_dates(self, market: MarketType, subject: SupplySubject) -> List[str]:
        """데이터가 존재하는 날짜 목록을 반환한다."""
        market_val = market.value if hasattr(market, 'value') else str(market)
        subject_val = subject.value if hasattr(subject, 'value') else str(subject)
        # 정규 형식(*_KOSPI_FOREIGN.json)과 구형 형식(*MarketType.KOSPI*.json) 모두 매칭 시도
        pattern = f"*{market_val}*{subject_val}*.json"
        files = self.root.glob(pattern)
        # 파일명에서 날짜 부분만 추출 (YYYY-MM-DD)
        return sorted([f.name.split('_')[0] for f in files], reverse=True)
