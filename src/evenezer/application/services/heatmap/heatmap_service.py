from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from evenezer.domain.heatmap.models import Heatmap, Stock, Theme, ThemeGroup
from evenezer.domain.heatmap.ports import ThemeDataLoaderPort
from evenezer.domain.heatmap.services import StockValidator, ThemeStatisticsService
from evenezer.domain.heatmap.theme_config import THEME_HIERARCHY, THEME_RENAME
from evenezer.domain.heatmap.value_objects import ChangeRatio, MarketCap
from evenezer.domain.ports import KrxDataPort


class HeatmapService:
    """히트맵 데이터 처리 서비스

    Application 레이어로서 유스케이스를 조율합니다.
    - Repository로부터 데이터 로드
    - Domain Model로 변환
    - Domain Service 활용
    """

    # 런타임 캐시 데이터 버퍼 (10분 만료 TTL)
    _cache_data: list[Theme] | None = None
    _expired_at: datetime | None = None

    def __init__(
        self,
        loader: ThemeDataLoaderPort | None = None,
        krx_repo: KrxDataPort | None = None,
        stock_validator: StockValidator | None = None
    ):
        if krx_repo:
            self.krx_repo = krx_repo
        else:
            from evenezer.infrastructure.adapters.heatmap.krx_repository import KrxRepository
            self.krx_repo = KrxRepository()

        if loader:
            self.file_repo = loader
        else:
            from evenezer.infrastructure.adapters.heatmap.file_repository import JsonThemeDataLoader

            # 전역 컨테이너 설정으로부터 드라이브 어댑터 및 히트맵 폴더 ID를 획득하여 주입
            from evenezer.infrastructure.container import container
            self.file_repo = JsonThemeDataLoader(
                json_dir=str(container.config.heatmap_dir),
                drive_adapter=container.drive_adapter,
                folder_id=container.config.heatmap_folder_id
            )

        self.theme_stats_service = ThemeStatisticsService()
        self.stock_validator = stock_validator if stock_validator else StockValidator()
        self._last_validation_report = pd.DataFrame()

    async def sync_from_drive(self) -> None:
        """구글 드라이브로부터 히트맵 테마 JSON 데이터들을 로컬로 동기화합니다."""
        if hasattr(self.file_repo, "sync_with_drive"):
            sync_func = getattr(self.file_repo, "sync_with_drive")
            if sync_func:
                await sync_func()

    def get_heatmap_data(self) -> pd.DataFrame:
        """히트맵 생성을 위한 최종 데이터를 반환합니다.

        하위 호환성을 위해 DataFrame을 반환하지만,
        내부적으로는 Domain Model을 사용합니다.
        """
        # 1. 도메인 모델로 변환
        themes = self._build_theme_models()

        if not themes:
            return pd.DataFrame()

        # 2. Domain Model -> DataFrame 변환 (하위 호환)
        return self._convert_themes_to_dataframe(themes)

    @classmethod
    def get_expired_at(cls) -> datetime | None:
        """캐시 만료 예정 일시를 반환합니다."""
        return cls._expired_at

    def get_themes(self, force_refresh: bool = False) -> list[Theme]:
        """도메인 모델로 테마 목록을 반환합니다. (10분 캐시 적용)"""
        now = datetime.now()

        # 0. 강제 새로고침이 요청된 경우 즉시 캐시 무효화
        if force_refresh:
            HeatmapService._cache_data = None
            HeatmapService._expired_at = None

        # 1. 캐시 만료 여부 확인 및 제거
        elif HeatmapService._expired_at and now >= HeatmapService._expired_at:
            HeatmapService._cache_data = None
            HeatmapService._expired_at = None

        # 2. 캐시가 비어있다면 신규 수집 후 캐싱
        if HeatmapService._cache_data is None:
            themes = self._build_theme_models()
            if themes:
                HeatmapService._cache_data = themes
                # 10분 후 만료 시각 설정
                HeatmapService._expired_at = now + timedelta(minutes=10)
            else:
                return []

        # 3. 유효한 캐시 즉시 반환
        return HeatmapService._cache_data

    def calculate_group_stats(self, df_final: pd.DataFrame) -> dict[str, dict[str, float]]:
        """테마 그룹별 통계를 계산합니다. (기존 API 유지)"""
        # DataFrame -> Domain Model 변환
        themes = self._dataframe_to_themes(df_final)

        # Domain Service 사용
        group_stats_models = self.theme_stats_service.calculate_group_stats(themes)

        # Domain Model -> Dict 변환 (하위 호환)
        result = {}
        for group_name, group in group_stats_models.items():
            result[group_name] = {
                'cap': group.market_cap.in_trillion,
                'change_sum': group.change_sum
            }

        return result

    def get_group_stats_models(self, themes: list[Theme]) -> dict[str, ThemeGroup]:
        """도메인 모델로 그룹 통계를 반환합니다."""
        return self.theme_stats_service.calculate_group_stats(themes)

    # === Private Methods ===

    def _build_theme_models(self) -> list[Theme]:
        """Repository로부터 데이터를 로드하여 Domain Model로 변환합니다."""
        # 1. Heatmap 로드 (테마 + 종목명)
        heatmap = self.file_repo.load_heatmap()

        if not heatmap.themes:
            return []

        # 2. KRX 데이터로 enrichment
        raw_krx = self.krx_repo.fetch_listing()
        if raw_krx is None:
            return []
        if isinstance(raw_krx, pd.DataFrame):
            if raw_krx.empty:
                return []
            df_krx = raw_krx
        else:
            if not raw_krx:
                return []
            df_krx = pd.DataFrame(raw_krx)

        self._enrich_heatmap_with_krx_data(heatmap, df_krx)

        # 유효성 검증 및 정제 (Invalid Stocks 제거)
        removed_df = self._clean_and_validate_heatmap(heatmap)
        self._last_validation_report = removed_df

        # 3. 테마명 변경 적용
        self._apply_theme_rename(heatmap)

        # 4. Theme 리스트 반환
        return list(heatmap.themes.values())

    def _enrich_heatmap_with_krx_data(self, heatmap: Heatmap, df_krx: pd.DataFrame) -> None:
        """Heatmap의 Stock 객체들을 KRX 데이터로 enrichment합니다.

        재귀적으로 계층 구조를 순회하며 종목 데이터를 업데이트하고,
        KRX 데이터에 없는 종목은 제거합니다.
        """
        # KRX 데이터를 종목명으로 조회 가능하도록 인덱싱
        krx_by_name = df_krx.set_index('Name').to_dict('index')

        for theme in heatmap.themes.values():
            valid_theme_stocks = [] # 테마 레벨의 유효 종목 리스트 (재구성)

            # 1. 카테고리 계층 구조 재귀적 순회 및 업데이트
            for category in theme.categories.values():
                self._enrich_category(category, krx_by_name, valid_theme_stocks)

            # 2. 테마의 Flat Stock List 교체
            theme.stocks = valid_theme_stocks

    def _enrich_category(self, category: Any, krx_data: dict[str, Any], valid_stocks_acc: list[Stock]) -> None:
        """카테고리 내의 종목을 업데이트하고 하위 카테고리를 재귀적으로 처리합니다."""
        # 1. 현재 카테고리의 종목 처리
        valid_category_stocks = []
        for stock in category.stocks:
            if stock.name in krx_data:
                kd = krx_data[stock.name]
                try:
                    # In-place 업데이트 (참조 유지)
                    stock.code = str(kd.get('Code', ''))
                    marcap = float(kd.get('Marcap', 0))
                    stock.market_cap = MarketCap(marcap) if marcap > 0 else MarketCap.zero()
                    stock.change_ratio = ChangeRatio(float(kd.get('ChagesRatio', 0)))

                    valid_category_stocks.append(stock)
                    if stock not in valid_stocks_acc:
                        valid_stocks_acc.append(stock)
                except (ValueError, KeyError):
                    continue
            else:
                # 매칭되지 않은 종목도 리스트에 유지하여 StockValidator가 정식으로 누락 리포트에 기록하게 양보
                stock.code = ""
                valid_category_stocks.append(stock)
                if stock not in valid_stocks_acc:
                    valid_stocks_acc.append(stock)

        # 임시로 모든 종목을 남기고 StockValidator 단계에서 최종 필터링되도록 위임
        category.stocks = valid_category_stocks

        # 2. 하위 카테고리 재귀 처리
        for child in category.children.values():
            self._enrich_category(child, krx_data, valid_stocks_acc)

    def get_validation_report(self) -> pd.DataFrame:
        """최근 검증에서 제외된 종목 리스트를 반환합니다."""
        if hasattr(self, '_last_validation_report'):
            return self._last_validation_report
        return pd.DataFrame()

    def _clean_and_validate_heatmap(self, heatmap: Heatmap) -> pd.DataFrame:
        """히트맵 데이터의 무결성을 검증하고 유효하지 않은 종목을 제거합니다."""
        removed_df = self.stock_validator.validate_and_clean_heatmap(heatmap)
        return removed_df

    def _apply_theme_rename(self, heatmap: Heatmap) -> None:
        """THEME_RENAME 설정에 따라 테마명을 변경합니다."""
        for old_name, new_name in THEME_RENAME.items():
            if old_name in heatmap.themes:
                theme = heatmap.themes[old_name]
                theme.name = new_name
                del heatmap.themes[old_name]
                heatmap.themes[new_name] = theme

    def _dataframe_to_themes(self, df: pd.DataFrame) -> list[Theme]:
        """DataFrame을 Domain Model(Theme 리스트)로 변환합니다."""
        themes_dict: dict[str, Theme] = {}

        for _, row in df.iterrows():
            theme_name = str(row.get('테마', ''))
            stock_name = str(row.get('종목명', row.get('Name', '')))
            code = str(row.get('Code', ''))

            marcap_value = float(row.get('Marcap', 0))
            market_cap = MarketCap(marcap_value) if marcap_value > 0 else MarketCap.zero()

            change_value = float(row.get('ChagesRatio', 0))
            try:
                change_ratio = ChangeRatio(change_value)
            except ValueError:
                change_ratio = ChangeRatio.zero()

            try:
                stock = Stock(
                    code=code,
                    name=stock_name,
                    market_cap=market_cap,
                    change_ratio=change_ratio
                )
            except ValueError:
                continue

            if theme_name not in themes_dict:
                theme = Theme(
                    name=theme_name,
                    parent_group=THEME_HIERARCHY.get(theme_name)
                )
                themes_dict[theme_name] = theme

            themes_dict[theme_name].add_stock(stock)

        return list(themes_dict.values())

    def _convert_themes_to_dataframe(self, themes: list[Theme]) -> pd.DataFrame:
        """Domain Model을 DataFrame으로 변환합니다. (하위 호환)"""
        rows = []

        for theme in themes:
            for stock in theme.stocks:
                rows.append({
                    '테마': theme.name,
                    '종목명': stock.name,
                    'Code': stock.code,
                    'Name': stock.name,
                    'Marcap': stock.market_cap.value_in_won,
                    '시가총액_조': stock.market_cap.in_trillion,
                    'ChagesRatio': stock.change_ratio.value
                })

        return pd.DataFrame(rows)
