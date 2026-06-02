"""
Domain Value Objects

불변 값 객체들을 정의합니다.
Value Object는 식별자가 없고 값 자체로 동일성을 판단합니다.
"""
from dataclasses import dataclass
from typing import Union


@dataclass(frozen=True)
class MarketCap:
    """시가총액 Value Object
    
    원 단위로 시가총액을 저장하며, 조 단위 변환 기능을 제공합니다.
    """
    value_in_won: float
    
    def __post_init__(self):
        if self.value_in_won < 0:
            raise ValueError("시가총액은 음수일 수 없습니다")
    
    @property
    def in_trillion(self) -> float:
        """조 단위로 변환된 시가총액"""
        return self.value_in_won / 1_000_000_000_000
    
    @property
    def in_billion(self) -> float:
        """억 단위로 변환된 시가총액"""
        return self.value_in_won / 100_000_000
    
    def __add__(self, other: 'MarketCap') -> 'MarketCap':
        """두 시가총액을 더합니다"""
        if not isinstance(other, MarketCap):
            raise TypeError("MarketCap끼리만 더할 수 있습니다")
        return MarketCap(self.value_in_won + other.value_in_won)
    
    def __mul__(self, scalar: Union[int, float]) -> 'MarketCap':
        """시가총액에 스칼라를 곱합니다"""
        return MarketCap(self.value_in_won * scalar)
    
    def __gt__(self, other: 'MarketCap') -> bool:
        return self.value_in_won > other.value_in_won
    
    def __lt__(self, other: 'MarketCap') -> bool:
        return self.value_in_won < other.value_in_won
    
    @classmethod
    def from_trillion(cls, value: float) -> 'MarketCap':
        """조 단위 값으로부터 생성"""
        return cls(value * 1_000_000_000_000)
    
    @classmethod
    def zero(cls) -> 'MarketCap':
        """0원 시가총액"""
        return cls(0.0)


@dataclass(frozen=True)
class ChangeRatio:
    """등락률 Value Object
    
    퍼센트 단위로 등락률을 저장합니다.
    """
    value: float  # 퍼센트 (예: 2.5는 2.5%)
    
    def __post_init__(self):
        # 등락률 범위 검증 (실무에서는 ±30% 제한 등)
        if abs(self.value) > 100:
            raise ValueError(f"등락률이 비정상적입니다: {self.value}%")
    
    def weighted_by(self, market_cap: MarketCap) -> float:
        """시가총액으로 가중된 등락률을 계산합니다
        
        가중 평균 계산 시 사용: (등락률 * 시가총액)
        """
        return self.value * market_cap.in_trillion
    
    @property
    def is_positive(self) -> bool:
        """상승 여부"""
        return self.value > 0
    
    @property
    def is_negative(self) -> bool:
        """하락 여부"""
        return self.value < 0
    
    @property
    def is_neutral(self) -> bool:
        """보합 여부"""
        return self.value == 0
    
    @classmethod
    def zero(cls) -> 'ChangeRatio':
        """보합 (0%)"""
        return cls(0.0)
