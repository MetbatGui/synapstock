import os
import json
import glob
from typing import List, Dict, Any
from synapstock.domain.heatmap.ports import ThemeDataLoaderPort
from synapstock.domain.heatmap.models import Heatmap, Theme, Category, Stock, MarketCap, ChangeRatio
import logging

logger = logging.getLogger(__name__)

class JsonThemeDataLoader(ThemeDataLoaderPort):
    """JSON 파일들에서 테마 계층 구조 데이터를 로드하는 어댑터"""
    
    def __init__(self, json_dir: str = 'data/heatmap'):
        self.json_dir = json_dir

    def load_heatmap(self) -> Heatmap:
        """JSON 파일들을 파싱하여 계층형 Heatmap 모델 반환"""
        heatmap = Heatmap()
        
        json_pattern = os.path.join(self.json_dir, "theme_*.json")
        files = glob.glob(json_pattern)
        
        if not files:
            logger.warning(f"{self.json_dir} 경로에 theme_*.json 파일이 없습니다.")
            return heatmap
            
        for file_path in files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._parse_theme_file(data, heatmap)
            except Exception as e:
                logger.error(f"{file_path} 파싱 실패: {e}")
                
        return heatmap

    def _parse_theme_file(self, data: Dict[str, Any], heatmap: Heatmap):
        theme_name = data.get('theme', 'Unknown')
        theme = Theme(name=theme_name)
        
        seen_categories = set()
        
        sectors = data.get('sectors', [])
        for sector_data in sectors:
            sector_name = sector_data.get('sector_name', 'Unknown')
            
            if sector_name in seen_categories:
                continue
            seen_categories.add(sector_name)
            
            category = Category(name=sector_name)
            
            if 'companies' in sector_data:
                self._add_companies(category, sector_data['companies'], theme)
                
            if 'categories' in sector_data:
                for sub_cat_1_data in sector_data['categories']:
                    self._parse_sub_category_1(sub_cat_1_data, category, theme, seen_categories)
            
            theme.add_category(category)
            
        heatmap.add_theme(theme)

    def _parse_sub_category_1(self, data: Dict[str, Any], parent_category: Category, theme: Theme, seen_categories: set):
        name = data.get('sub_category_1', 'Unknown')
        
        if name in seen_categories:
            return
        seen_categories.add(name)
        
        category = Category(name=name)
        
        if 'companies' in data:
            self._add_companies(category, data['companies'], theme)
            
        if 'sub_categories_2' in data:
            for sub_cat_2_data in data['sub_categories_2']:
                self._parse_sub_category_2(sub_cat_2_data, category, theme, seen_categories)
                
        parent_category.add_child(category)

    def _parse_sub_category_2(self, data: Dict[str, Any], parent_category: Category, theme: Theme, seen_categories: set):
        name = data.get('name', 'Unknown')
        
        if name in seen_categories:
            return
        seen_categories.add(name)
        
        category = Category(name=name)
        
        if 'companies' in data:
             self._add_companies(category, data['companies'], theme)
             
        parent_category.add_child(category)

    def _add_companies(self, category: Category, company_names: List[str], theme: Theme):
        for name_entry in company_names:
            name_entry = name_entry.strip()
            if ":" in name_entry:
                name, code = name_entry.split(":", 1)
                name = name.strip()
                code = code.strip()
            else:
                name = name_entry
                code = "TBD"
                
            stock = Stock(
                code=code,
                name=name,
                market_cap=MarketCap.zero(),
                change_ratio=ChangeRatio.zero()
            )
            category.add_stock(stock)
            theme.add_stock(stock)
