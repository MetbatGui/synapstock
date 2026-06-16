from typing import List, Dict
import pandas as pd
from .models import Theme, ThemeGroup, Stock, Heatmap, Category
from .theme_config import THEME_HIERARCHY
from .value_objects import MarketCap


class StockValidator:
    """도메인 종목 유효성 검증 및 데이터 정제를 전담하는 도메인 서비스"""
    
    def validate_and_clean_heatmap(self, heatmap: Heatmap) -> pd.DataFrame:
        """히트맵 데이터의 무결성을 검증하고 유효하지 않은 종목을 제거합니다.
        
        Args:
            heatmap: 검증 및 정제를 수행할 Heatmap 도메인 모델
            
        Returns:
            pd.DataFrame: 제외된 종목들의 내역이 담긴 DataFrame
                          (Theme, Category, StockName, Code, Reason, Value)
        """
        removed_records = []
        seen_removed_codes = set()
        
        for theme in heatmap.themes.values():
            # 1. 카테고리 계층 구조 정제 (재귀)
            for category in theme.categories.values():
                self._clean_category_recursively(theme.name, category, removed_records, seen_removed_codes)
            
            # 정제 후 비어 있게 된 카테고리 트리 제거 (Pruning)
            self._prune_empty_categories(theme)
            
            # 2. 테마 Flat List 정제
            valid_theme_stocks = []
            for stock in theme.stocks:
                if self._is_stock_valid(stock):
                    valid_theme_stocks.append(stock)
                else:
                    if stock.code not in seen_removed_codes:
                        removed_records.append({
                            'Theme': theme.name,
                            'Category': 'Root(Flat)',
                            'StockName': stock.name,
                            'Code': stock.code,
                            'Reason': 'Invalid Data (Zero Market Cap or Missing Code)',
                            'Value': stock.market_cap.value_in_won
                        })
                        seen_removed_codes.add(stock.code)
            theme.stocks = valid_theme_stocks
            
        return pd.DataFrame(removed_records)

    def _prune_empty_categories(self, theme: Theme) -> None:
        """종목이 모두 정제되어 비어 있게 된 카테고리를 재귀적으로 트리에서 제거합니다."""
        
        def prune_category(category: Category) -> bool:
            # 1. 하위 카테고리부터 재귀적으로 먼저 프루닝 수행
            empty_children = []
            for child_name, child in list(category.children.items()):
                should_remove = prune_category(child)
                if should_remove:
                    empty_children.append(child_name)
                    
            for child_name in empty_children:
                del category.children[child_name]
                
            # 2. 하위 카테고리도 없고 가지고 있는 종목도 없으면 True 반환하여 삭제 대상임을 알림
            return (not category.stocks) and (not category.children)

        # Theme.categories 딕셔너리 최상위 레벨 프루닝
        empty_root_cats = []
        for cat_name, category in list(theme.categories.items()):
            should_remove = prune_category(category)
            if should_remove:
                empty_root_cats.append(cat_name)
                
        for cat_name in empty_root_cats:
            del theme.categories[cat_name]

    def _clean_category_recursively(
        self, 
        theme_name: str, 
        category: Category, 
        removed_records: List[Dict], 
        seen_codes: set
    ) -> None:
        """재귀적으로 카테고리를 순회하며 유효하지 않은 종목을 제거합니다."""
        valid_stocks = []
        for stock in category.stocks:
            if self._is_stock_valid(stock):
                valid_stocks.append(stock)
            else:
                if stock.code not in seen_codes:
                    removed_records.append({
                        'Theme': theme_name,
                        'Category': category.name,
                        'StockName': stock.name,
                        'Code': stock.code,
                        'Reason': 'Invalid Data (Zero Market Cap or Missing Code)',
                        'Value': stock.market_cap.value_in_won
                    })
                    seen_codes.add(stock.code)
        category.stocks = valid_stocks
        
        for child in category.children.values():
            self._clean_category_recursively(theme_name, child, removed_records, seen_codes)

    def _is_stock_valid(self, stock: Stock) -> bool:
        """종목 데이터의 유효성을 검사합니다."""
        if not stock.code or stock.code == 'None':
             return False
        # 시가총액이 0 이하면 제외
        if stock.market_cap.value_in_won <= 0:
            return False
        return True


class ThemeStatisticsService:
    """테마 통계 계산 도메인 서비스"""
    
    @staticmethod
    def calculate_group_stats(themes: List[Theme]) -> Dict[str, ThemeGroup]:
        """계층 구조를 고려한 그룹 통계 계산
        
        Args:
            themes: 테마 목록
            
        Returns:
            그룹명을 키로, ThemeGroup 통계를 값으로 하는 딕셔너리
        """
        group_stats: Dict[str, Dict[str, float]] = {}
        
        for theme in themes:
            parent_group = theme.parent_group or THEME_HIERARCHY.get(theme.name)
            
            if not parent_group:
                continue
            
            theme_mkt_cap = theme.total_market_cap
            theme_change_sum = sum(stock.weighted_change() for stock in theme.stocks)
            
            if parent_group not in group_stats:
                group_stats[parent_group] = {'cap': 0, 'change_sum': 0}
            
            group_stats[parent_group]['cap'] += theme_mkt_cap.in_trillion
            group_stats[parent_group]['change_sum'] += theme_change_sum
        
        # ThemeGroup 객체로 변환
        result = {}
        for group_name, stats in group_stats.items():
            result[group_name] = ThemeGroup(
                name=group_name,
                market_cap=MarketCap.from_trillion(stats['cap']),
                change_sum=stats['change_sum']
            )
        
        return result
    
    @staticmethod
    def sort_themes_by_market_cap(themes: List[Theme], descending: bool = True) -> List[Theme]:
        """시가총액 순으로 테마 정렬
        
        Args:
            themes: 테마 목록
            descending: True면 내림차순, False면 오름차순
            
        Returns:
            정렬된 테마 목록
        """
        return sorted(
            themes,
            key=lambda t: t.total_market_cap.value_in_won,
            reverse=descending
        )
    
    @staticmethod
    def filter_themes_by_min_stocks(themes: List[Theme], min_stocks: int) -> List[Theme]:
        """최소 종목 수로 테마 필터링
        
        Args:
            themes: 테마 목록
            min_stocks: 최소 종목 수
            
        Returns:
            필터링된 테마 목록
        """
        return [theme for theme in themes if theme.stock_count >= min_stocks]
    
    @staticmethod
    def get_top_stocks_by_market_cap(theme: Theme, top_n: int) -> List[Stock]:
        """테마 내 시가총액 상위 N개 종목 반환
        
        Args:
            theme: 테마
            top_n: 상위 N개
            
        Returns:
            시가총액 상위 종목 목록
        """
        return sorted(
            theme.stocks,
            key=lambda s: s.market_cap.value_in_won,
            reverse=True
        )[:top_n]
