import json
import os
from pathlib import Path
from typing import Dict, List, Optional

class LocalMarketDataRepository:
    """KRX에서 수집한 전종목 시세 및 수급 데이터를 로컬 파일로 관리하는 저장소."""

    def __init__(self, base_dir: str = "data/market/raw"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_raw_data(self, date_str: str, category: str, data: any):
        """특정 날짜와 카테고리(prices, supply_demand 등)의 원천 데이터를 저장한다."""
        date_dir = self.base_dir / date_str
        date_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = date_dir / f"{category}.json"
        
        with open(file_path, "w", encoding="utf-8") as f:
            if isinstance(data, (list, dict)):
                json.dump(data, f, indent=2, ensure_ascii=False)
            else:
                f.write(str(data))

    def load_raw_data(self, date_str: str, category: str) -> Optional[any]:
        """저장된 원천 데이터를 로드한다."""
        file_path = self.base_dir / date_str / f"{category}.json"
        if not file_path.exists():
            return None
            
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def list_available_dates(self) -> List[str]:
        """데이터가 존재하는 날짜 목록을 반환한다."""
        if not self.base_dir.exists():
            return []
        
        dates = [d.name for d in self.base_dir.iterdir() if d.is_dir()]
        return sorted(dates, reverse=True)
