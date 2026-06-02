"""
Application Layer - ViewModel 변환기

Domain Model을 Presentation ViewModel로 변환하는 로직입니다.
"""
from typing import List, Dict
from synapstock.domain.heatmap.models import Theme, ThemeGroup
from synapstock.presentation.web.routes.heatmap.view_models import HeatmapViewModel, TreemapNode
from synapstock.domain.heatmap.theme_config import THEME_HIERARCHY


class HeatmapViewModelBuilder:
    """히트맵 ViewModel 생성기
    
    Domain Model을 Presentation 레이어의 ViewModel로 변환합니다.
    """
    
    @staticmethod
    def build(themes: List[Theme], group_stats: Dict[str, ThemeGroup], show_categories: bool = True, show_stocks: bool = False) -> HeatmapViewModel:
        """Domain Model로부터 HeatmapViewModel을 생성합니다.
        
        Args:
            themes: 테마 목록
            group_stats: 그룹 통계
            show_categories: 카테고리 계층 표시 여부
            show_stocks: 종목 상세 노드 표시 여부
            
        Returns:
            HeatmapViewModel
        """
        nodes: List[TreemapNode] = []
        root_id = "KRX_Themes"
        
        # 1. Root 노드
        total_mkt_cap_calc = sum(theme.total_market_cap.in_trillion for theme in themes)
        
        if total_mkt_cap_calc > 0:
            weighted_sum = sum(
                stock.weighted_change() 
                for theme in themes 
                for stock in theme.stocks
            )
            total_change = weighted_sum / total_mkt_cap_calc
        else:
            total_change = 0.0
        
        nodes.append(TreemapNode(
            id=root_id,
            label="대한민국 테마별 증시",
            parent_id="",
            value=total_mkt_cap_calc,
            color=round(total_change, 2),
            custom_data=round(total_change, 2),
            text_template="<b>%{label}</b><br>%{value:.2f}조<br>%{customdata:.2f}%",
            ticker=""
        ))
        
        # 2. 그룹 노드 (중간 계층)
        for group_name, group in group_stats.items():
            group_id = f"Group_{group_name}"
            group_value = group.market_cap.in_trillion
            
            nodes.append(TreemapNode(
                id=group_id,
                label=group_name,
                parent_id=root_id,
                value=group_value,
                color=round(group.weighted_change_ratio, 2),
                custom_data=round(group.weighted_change_ratio, 2),
                text_template="<b>%{label}</b><br>%{value:.2f}조<br>%{customdata:.2f}%",
                ticker=""
            ))
        
        # 3. 테마 노드
        for theme in themes:
            group_name = theme.parent_group or THEME_HIERARCHY.get(theme.name)
            parent_id = f"Group_{group_name}" if group_name else root_id
            theme_id = f"Theme_{theme.name}"
            
            nodes.append(TreemapNode(
                id=theme_id,
                label=theme.name,
                parent_id=parent_id,
                value=theme.total_market_cap.in_trillion,
                color=round(theme.weighted_change_ratio, 2),
                custom_data=round(theme.weighted_change_ratio, 2),
                text_template="<b>%{label}</b><br>%{value:.2f}조<br>%{customdata:.2f}%",
                ticker=""
            ))

        # 4. 하위 계층 (카테고리 및 종목)
        for theme in themes:
            theme_id = f"Theme_{theme.name}"
            
            if theme.categories and show_categories:
                # 카테고리가 있는 경우 (JSON 데이터)
                for category in theme.categories.values():
                    HeatmapViewModelBuilder._add_category_nodes(
                        nodes, category, theme_id, theme.name, show_stocks
                    )
            elif show_stocks:
                # 카테고리가 없거나 표시 안 함 + 종목은 표시함 (Flat 구조)
                for stock in theme.stocks:
                    stock_id = f"{theme_id}_{stock.name}"
                    
                    nodes.append(TreemapNode(
                        id=stock_id,
                        label=stock.name,
                        parent_id=theme_id,
                        value=stock.market_cap.in_trillion,
                        color=round(stock.change_ratio.value, 2),
                        custom_data=round(stock.change_ratio.value, 2),
                        text_template="<b>%{label}</b><br>%{value:.2f}조<br>%{customdata:.2f}%",
                        ticker=stock.code
                    ))
        
        # 검증: 부모-자식 합계 일치 확인 (개발 모드)
        if __debug__:
            HeatmapViewModelBuilder._validate_parent_child_sums(nodes)
        
        return HeatmapViewModel(nodes=nodes)

    @staticmethod
    def _add_category_nodes(nodes: List[TreemapNode], category, parent_id: str, theme_name: str, show_stocks: bool):
        """재귀적으로 카테고리 노드와 하위 종목/카테고리를 추가합니다."""
        category_id = f"{parent_id}_{category.name}"
        cat_value = category.total_market_cap.in_trillion
        
        if show_stocks:
            cat_text = "<b>%{label}</b>"
        else:
            cat_text = "<b>%{label}</b><br>%{value:.2f}조<br>%{customdata:.2f}%"
        
        nodes.append(TreemapNode(
            id=category_id,
            label=category.name,
            parent_id=parent_id,
            value=cat_value,
            color=round(category.weighted_change_ratio, 2),
            custom_data=round(category.weighted_change_ratio, 2),
            text_template=cat_text,
            ticker=""
        ))
        
        # 1. 하위 카테고리 처리 (재귀)
        for child in category.children.values():
            HeatmapViewModelBuilder._add_category_nodes(
                nodes, child, category_id, theme_name, show_stocks
            )
            
        # 2. 소속 종목 처리
        if show_stocks:
            for stock in category.stocks:
                stock_id = f"{category_id}_{stock.name}"
                
                nodes.append(TreemapNode(
                    id=stock_id,
                    label=stock.name,
                    parent_id=category_id,
                    value=stock.market_cap.in_trillion,
                    color=round(stock.change_ratio.value, 2),
                    custom_data=round(stock.change_ratio.value, 2),
                    text_template="<b>%{label}</b><br>%{value:.2f}조<br>%{customdata:.2f}%",
                    ticker=stock.code
                ))
    
    @staticmethod
    def _validate_parent_child_sums(nodes: List[TreemapNode], tolerance: float = 0.01):
        """부모-자식 합계 일치 검증"""
        # 부모별 자식 합계 계산
        parent_to_children = {}
        for node in nodes:
            if node.parent_id:
                if node.parent_id not in parent_to_children:
                    parent_to_children[node.parent_id] = []
                parent_to_children[node.parent_id].append(node.value)
        
        # 부모 노드와 자식 합계 비교
        mismatches = []
        for node in nodes:
            if node.id in parent_to_children:
                children_sum = sum(parent_to_children[node.id])
                diff = abs(node.value - children_sum)
                if diff > tolerance:
                    mismatches.append({
                        'parent': node.label,
                        'parent_value': node.value,
                        'children_sum': children_sum,
                        'diff': diff
                    })
        
        if mismatches:
            # synapstock 로깅을 지원하기 위해 지연/동적 로깅 시도
            try:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"부모-자식 합계 불일치 발견: {len(mismatches)}건")
                for m in mismatches[:5]:
                    logger.warning(
                        f"  - {m['parent']}: 부모={m['parent_value']:.2f}조, "
                        f"자식합={m['children_sum']:.2f}조, 차이={m['diff']:.2f}조"
                    )
            except Exception:
                pass
