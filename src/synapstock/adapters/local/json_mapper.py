import json
from pathlib import Path
from typing import Any
from synapstock.domain.models import Board, Node, Stock

class JsonThemeMapper:
    """theme_*.json 파일을 Board 도메인 모델로 변환하는 매퍼."""

    @staticmethod
    def from_json(file_path: str | Path) -> Board:
        """JSON 파일을 읽어서 Board 객체로 변환한다."""
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        theme_name = data.get("theme", "Unknown")
        board = Board(name=theme_name)
        
        # 루트 노드 아래에 sectors 추가
        for sector_data in data.get("sectors", []):
            sector_node = board.root.add_child(sector_data.get("sector_name", "Untitled Sector"))
            JsonThemeMapper._parse_recursive(sector_node, sector_data)
            
        return board

    @staticmethod
    def _parse_recursive(parent_node: Node, data: dict[str, Any]):
        """JSON 데이터를 재귀적으로 파싱하여 트리를 구성한다."""
        
        # 1. Companies (Stocks) 추가
        companies = data.get("companies", [])
        for company_name in companies:
            parent_node.stocks.append(Stock(name=company_name, ticker="000000"))

        # 2. 하위 카테고리/섹터/노드 탐색 (무제한 Depth)
        # 다양한 키 패턴(sectors, categories, sub_categories_n, nodes 등)을 모두 지원
        child_keys = ["sectors", "categories", "sub_categories_2", "sub_categories", "nodes"]
        
        # 명시적인 키 외에도 리스트 형태의 값을 가진 모든 키를 후보로 검토
        for key, value in data.items():
            if key in child_keys or (isinstance(value, list) and key not in ["companies", "company_names"]):
                for item in value:
                    if isinstance(item, dict):
                        # 이름 키 찾기 (sector_name -> sub_category_1 -> name 순)
                        name = item.get("sector_name") or item.get("sub_category_1") or item.get("name") or "Untitled"
                        # 중복 노드 방지
                        child_node = parent_node.add_child(name)
                        JsonThemeMapper._parse_recursive(child_node, item)
