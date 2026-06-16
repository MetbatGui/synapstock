"""
Presentation Layer View Models

Presentation 레이어를 위한 데이터 전송 객체(DTO)입니다.
"""
from dataclasses import dataclass
from typing import List


@dataclass
class TreemapNode:
    """Treemap 노드 데이터"""
    id: str
    label: str
    parent_id: str
    value: float  # 시가총액 (조 단위)
    color: float  # 등락률 (%)
    custom_data: float  # 추가 데이터
    text_template: str  # 표시 템플릿
    ticker: str = ""   # 종목 코드 (주식 노드일 때만 존재, 없으면 빈 문자열)


@dataclass
class HeatmapViewModel:
    """히트맵 시각화를 위한 ViewModel
    
    Domain Model을 Presentation 레이어에서 사용하기 위한 형태로 변환한 데이터입니다.
    """
    nodes: List[TreemapNode]
    root_label: str = "대한민국 테마별 증시"
    title: str = "대한민국 테마별 증시 히트맵"
    
    def get_ids(self) -> List[str]:
        """모든 노드의 ID 리스트"""
        return [node.id for node in self.nodes]
    
    def get_labels(self) -> List[str]:
        """모든 노드의 라벨 리스트"""
        return [node.label for node in self.nodes]
    
    def get_parents(self) -> List[str]:
        """모든 노드의 부모 ID 리스트"""
        return [node.parent_id for node in self.nodes]
    
    def get_values(self) -> List[float]:
        """모든 노드의 값 리스트"""
        return [node.value for node in self.nodes]
    
    def get_colors(self) -> List[float]:
        """모든 노드의 색상 값 리스트"""
        return [node.color for node in self.nodes]
    
    def get_custom_data(self) -> List[float]:
        """모든 노드의 커스텀 데이터 리스트"""
        return [node.custom_data for node in self.nodes]
    
    def get_text_templates(self) -> List[str]:
        """모든 노드의 텍스트 템플릿 리스트"""
        return [node.text_template for node in self.nodes]
        
    def get_tickers(self) -> List[str]:
        """모든 노드의 티커 코드 리스트"""
        return [node.ticker for node in self.nodes]
