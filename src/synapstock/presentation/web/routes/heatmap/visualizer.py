import plotly.graph_objects as go
import pandas as pd
import os
from synapstock.presentation.web.routes.heatmap.view_models import HeatmapViewModel

class HeatmapVisualizer:
    """히트맵 시각화 클래스
    
    Presentation 레이어로서 순수하게 시각화만 담당합니다.
    비즈니스 로직은 포함하지 않으며, ViewModel을 받아 Plotly 차트를 생성합니다.
    """
    
    def create_treemap_from_viewmodel(
        self, 
        view_model: HeatmapViewModel, 
        output_file: str = 'theme_heatmap.html',
        initial_depth: int = 3
    ):
        """ViewModel을 기반으로 Plotly Treemap을 생성하고 저장합니다.
        
        Args:
            view_model: HeatmapViewModel
            output_file: 출력 파일명
            initial_depth: 초기 표시 깊이 (기본값: 3 = Root + Group + Theme)
                          클릭 시 하위 레벨로 drill-down됨
        """
        custom_colorscale = [
            [0.0, 'blue'],
            [0.5, '#444444'],
            [1.0, 'red']
        ]
        
        fig = go.Figure(go.Treemap(
            ids=view_model.get_ids(),
            labels=view_model.get_labels(),
            parents=view_model.get_parents(),
            values=view_model.get_values(),
            branchvalues='total',  # 타일 구조: 부모 노드 값은 자식 노드 합계와 일치 (빈 공간 제거)
            maxdepth=2,  # 같은 depth의 항목들만 표시 (클릭 시 drill-down)
            marker=dict(
                colors=view_model.get_colors(),
                colorscale=custom_colorscale,
                cmid=0,
                cmin=-15,
                cmax=15,
                colorbar=dict(title="등락률(%)")
            ),
            customdata=view_model.get_custom_data(),
            texttemplate=view_model.get_text_templates(),
            hovertemplate='<b>%{label}</b><br>시가총액: %{value:.2f}조 원<br>등락률: %{customdata:.2f}%<extra></extra>',
            textposition='middle center'
        ))
        
        fig.update_layout(
            title=view_model.title + " (테마를 클릭하여 상세 보기)",
            margin=dict(t=50, l=10, r=10, b=10),
            font=dict(family="Malgun Gothic", size=18)
        )
        
        fig.write_html(output_file)
        print(f"\n히트맵 생성 완료: {output_file}")
        
        # 브라우저 자동 실행 (도커/서버 환경 등 Headless 환경에서는 건너뜀)
        if "SYNAPSTOCK_HOST" not in os.environ:
            try:
                os.startfile(output_file)
            except AttributeError:
                try:
                    import webbrowser
                    webbrowser.open(output_file)
                except Exception:
                    pass
    
    def create_treemap(self, df_final: pd.DataFrame, group_stats: dict, output_file: str = 'theme_heatmap.html'):
        """데이터프레임을 기반으로 Plotly Treemap을 생성하고 저장합니다. (기존 API - 하위 호환)
        
        DEPRECATED: 하위 호환을 위해 유지하지만, create_treemap_from_viewmodel 사용을 권장합니다.
        """
        from synapstock.domain.heatmap.theme_config import THEME_HIERARCHY
        
        ids = []
        labels = []
        parents = []
        values = []
        colors = []
        custom_data = []
        text_templates = []
        
        root_id = "KRX_Themes"
        root_label = "대한민국 테마별 증시"
        
        # 1. Root 노드
        ids.append(root_id)
        labels.append(root_label)
        parents.append("")
        
        total_mkt_cap = df_final['시가총액_조'].sum()
        total_change = (df_final['ChagesRatio'] * df_final['시가총액_조']).sum() / total_mkt_cap if total_mkt_cap > 0 else 0
        
        values.append(total_mkt_cap)
        colors.append(total_change)
        custom_data.append(total_change)
        text_templates.append("<b>%{label}</b>")
        
        # 2. 테마(Branch) 노드
        theme_groups = df_final.groupby('테마')
        
        for theme_name, group in theme_groups:
            parent_group = THEME_HIERARCHY.get(theme_name)
            
            theme_mkt_cap = group['시가총액_조'].sum()
            theme_change_sum = (group['ChagesRatio'] * group['시가총액_조']).sum()
            theme_change = theme_change_sum / theme_mkt_cap if theme_mkt_cap > 0 else 0
            
            if parent_group:
                parent_id = f"Group_{parent_group}"
            else:
                parent_id = root_id
                
            theme_id = f"Theme_{theme_name}"
            
            ids.append(theme_id)
            labels.append(theme_name)
            parents.append(parent_id)
            values.append(theme_mkt_cap)
            colors.append(theme_change)
            custom_data.append(theme_change)
            text_templates.append("<b>%{label}</b>")
            
        # 3. 중간 그룹 노드 (예: '2차전지')
        for group_name, stats in group_stats.items():
            group_id = f"Group_{group_name}"
            
            group_cap = stats['cap']
            group_change = stats['change_sum'] / group_cap if group_cap > 0 else 0
                
            ids.append(group_id)
            labels.append(group_name)
            parents.append(root_id)
            values.append(group_cap)
            colors.append(group_change)
            custom_data.append(group_change)
            text_templates.append("<b>%{label}</b>")
            
        # 4. 종목(Leaf) 노드
        for _, row in df_final.iterrows():
            stock_name = row['종목명']
            theme_name = row['테마']
            
            stock_id = f"{theme_name}_{stock_name}"
            parent_id = f"Theme_{theme_name}"
            
            ids.append(stock_id)
            labels.append(stock_name)
            parents.append(parent_id)
            values.append(row['시가총액_조'])
            colors.append(row['ChagesRatio'])
            custom_data.append(row['ChagesRatio'])
            text_templates.append("<b>%{label}</b><br>%{value:.2f}조<br>%{customdata:.2f}%")
            
        # 5. 시각화 생성
        custom_colorscale = [
            [0.0, 'blue'],
            [0.5, '#444444'],
            [1.0, 'red']
        ]
        
        fig = go.Figure(go.Treemap(
            ids=ids,
            labels=labels,
            parents=parents,
            values=values,
            branchvalues='total',
            maxdepth=2,  # [FIX] 최대 깊이를 2로 제한 (레거시 지원)
            marker=dict(
                colors=colors,
                colorscale=custom_colorscale,
                cmid=0,
                cmin=-15,
                cmax=15,
                colorbar=dict(title="등락률(%)")
            ),
            customdata=custom_data,
            texttemplate=text_templates,
            hovertemplate='<b>%{label}</b><br>시가총액: %{value:.2f}조 원<br>등락률: %{customdata:.2f}%<extra></extra>',
            textposition='middle center'
        ))
        
        fig.update_layout(
            title='대한민국 테마별 증시 히트맵',
            margin=dict(t=50, l=10, r=10, b=10),
            font=dict(family="Malgun Gothic", size=18)
        )
        
        fig.write_html(output_file)
        print(f"\n히트맵 생성 완료: {output_file}")
        
        # 브라우저 자동 실행 (도커/서버 환경 등 Headless 환경에서는 건너뜀)
        if "SYNAPSTOCK_HOST" not in os.environ:
            try:
                os.startfile(output_file)
            except AttributeError:
                try:
                    import webbrowser
                    webbrowser.open(output_file)
                except Exception:
                    pass
