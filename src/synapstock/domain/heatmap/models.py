"""
Domain Models (Entities)

엔티티는 식별자를 가지며 생명주기 동안 추적됩니다.
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict
from .value_objects import MarketCap, ChangeRatio


@dataclass
class Stock:
    """주식 종목 엔티티
    
    종목 코드로 식별되는 엔티티입니다.
    """
    code: str  # 식별자
    name: str
    market_cap: MarketCap
    change_ratio: ChangeRatio
    theme: Optional['Theme'] = None
    
    def __post_init__(self):
        if not self.code:
            raise ValueError("종목 코드는 필수입니다")
        if not self.name:
            raise ValueError("종목명은 필수입니다")
    
    @property
    def market_cap_trillion(self) -> float:
        """시가총액 (조 단위) - 하위 호환성 유지"""
        return self.market_cap.in_trillion
    
    def weighted_change(self) -> float:
        """시가총액으로 가중된 등락률"""
        return self.change_ratio.weighted_by(self.market_cap)


@dataclass
class Category:
    """테마 내 하위 카테고리 (재귀적 구조)"""
    name: str # 식별자
    stocks: List[Stock] = field(default_factory=list)
    children: Dict[str, 'Category'] = field(default_factory=dict)
    
    def add_stock(self, stock: Stock) -> None:
        if stock not in self.stocks:
            self.stocks.append(stock)
            
    def add_child(self, category: 'Category') -> None:
        self.children[category.name] = category
        
    @property
    def total_market_cap(self) -> MarketCap:
        total = MarketCap.zero()
        for stock in self.stocks:
            total = total + stock.market_cap
        for child in self.children.values():
            total = total + child.total_market_cap
        return total

    @property
    def weighted_change_ratio(self) -> float:
        """가중 평균 등락률 (재귀적으로 계산)"""
        total_cap = self.total_market_cap
        if total_cap.value_in_won == 0:
            return 0.0
        
        return self._calculate_weighted_sum() / total_cap.in_trillion
        
    def _calculate_weighted_sum(self) -> float:
        current_sum = sum(stock.weighted_change() for stock in self.stocks)
        child_sum = sum(child._calculate_weighted_sum() for child in self.children.values())
        return current_sum + child_sum


@dataclass
class Theme:
    """테마 엔티티
    
    테마명으로 식별되며 여러 종목과 카테고리를 포함합니다.
    """
    name: str  # 식별자
    stocks: List[Stock] = field(default_factory=list) # 전체 종목 리스트 (Flattened)
    categories: Dict[str, Category] = field(default_factory=dict) # 상위 카테고리 (Sectors in JSON)
    parent_group: Optional[str] = None
    
    def __post_init__(self):
        if not self.name:
            raise ValueError("테마명은 필수입니다")
    
    def add_stock(self, stock: Stock) -> None:
        """종목 추가 (Flat List)"""
        if stock not in self.stocks:
            self.stocks.append(stock)
            stock.theme = self
    
    def add_category(self, category: Category) -> None:
        self.categories[category.name] = category
            
    def remove_stock(self, stock: Stock) -> None:
        """종목 제거"""
        if stock in self.stocks:
            self.stocks.remove(stock)
            stock.theme = None
    
    @property
    def total_market_cap(self) -> MarketCap:
        """테마 내 총 시가총액
        
        카테고리 구조가 있으면 카테고리 합계를 사용하고,
        없으면 stocks 합계를 사용합니다. (부모-자식 합계 일치 보장)
        """
        if not self.stocks:
            return MarketCap.zero()
        
        # 카테고리 구조가 있으면 카테고리 합계 사용 (계층 구조 우선)
        if self.categories:
            total = MarketCap.zero()
            for category in self.categories.values():
                total = total + category.total_market_cap
            return total
        
        # 카테고리가 없으면 Flat stocks 합계 사용
        total = MarketCap.zero()
        for stock in self.stocks:
            total = total + stock.market_cap
        return total
    
    @property
    def weighted_change_ratio(self) -> float:
        """가중 평균 등락률"""
        if not self.stocks:
            return 0.0
        
        total_cap = self.total_market_cap
        if total_cap.value_in_won == 0:
            return 0.0
        
        weighted_sum = sum(stock.weighted_change() for stock in self.stocks)
        return weighted_sum / total_cap.in_trillion
    
    @property
    def stock_count(self) -> int:
        """종목 개수 (categories에 있는 종목 포함)"""
        # Flat stocks가 있으면 그것을 사용
        if self.stocks:
            return len(self.stocks)
        
        # categories에서 재귀적으로 종목 수 계산
        if self.categories:
            def count_category_stocks(category):
                count = len(category.stocks)
                for child in category.children.values():
                    count += count_category_stocks(child)
                return count
            
            return sum(count_category_stocks(cat) for cat in self.categories.values())
        
        return 0


@dataclass
class Heatmap:
    """히트맵 루트 엔티티"""
    themes: Dict[str, Theme] = field(default_factory=dict)
    
    @property
    def total_market_cap(self) -> MarketCap:
        total = MarketCap.zero()
        for theme in self.themes.values():
            total = total + theme.total_market_cap
        return total
        
    @property
    def weighted_change_ratio(self) -> float:
        total_cap = self.total_market_cap
        if total_cap.value_in_won == 0:
            return 0.0
            
        weighted_sum = 0.0
        for theme in self.themes.values():
             weighted_sum += sum(stock.weighted_change() for stock in theme.stocks)
             
        return weighted_sum / total_cap.in_trillion
    
    def add_theme(self, theme: Theme) -> None:
        self.themes[theme.name] = theme


@dataclass
class ThemeGroup:
    """테마 그룹 데이터 클래스 (집계용 - 레거시 지원 고려)
    
    여러 테마를 그룹화한 통계 정보를 저장합니다.
    """
    name: str
    market_cap: MarketCap
    change_sum: float  # 가중 평균 계산용 (등락률 * 시가총액) 합계
    
    @property
    def weighted_change_ratio(self) -> float:
        """가중 평균 등락률"""
        if self.market_cap.value_in_won == 0:
            return 0.0
        return self.change_sum / self.market_cap.in_trillion
