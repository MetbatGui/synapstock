import glob
import json
import logging
import os
from typing import Any

from evenezer.domain.heatmap.models import Category, ChangeRatio, Heatmap, MarketCap, Stock, Theme
from evenezer.domain.heatmap.ports import ThemeDataLoaderPort

logger = logging.getLogger(__name__)

class JsonThemeDataLoader(ThemeDataLoaderPort):
    """JSON 파일들을 로드하고 파싱하여 히트맵(Heatmap) 도메인 모델을 구축하는 어댑터입니다."""

    def __init__(self, json_dir: str = 'data/heatmap', drive_adapter = None, folder_id: str | None = None):
        """JsonThemeDataLoader를 초기화합니다.

        Args:
            json_dir: 로컬 히트맵 JSON 파일들이 저장되는 디렉토리 경로. 기본값은 'data/heatmap'.
            drive_adapter: 구글 드라이브 동기화를 위한 드라이브 어댑터.
            folder_id: 구글 드라이브 내 히트맵 파일이 저장된 폴더 ID.
        """
        self.json_dir = json_dir
        self.drive_adapter = drive_adapter
        self.folder_id = folder_id

    async def sync_with_drive(self) -> None:
        """구글 드라이브 폴더로부터 theme_*.json 파일들을 로컬 디렉토리로 동기화합니다.

        스마트 캐싱을 적용하여 파일 수정 시각이 변경된 경우에만 다운로드를 실행하며,
        구글 드라이브에서 삭제된 파일은 로컬에서도 정리(cleanup)합니다.
        """
        if not self.drive_adapter or not self.folder_id:
            logger.info("[JsonThemeDataLoader] 드라이브 어댑터 또는 히트맵 폴더 ID가 지정되지 않아 동기화를 생략합니다.")
            return

        from pathlib import Path
        local_dir = Path(self.json_dir)
        local_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 드라이브 파일 목록 가져오기
            files = await self.drive_adapter.list_files_in_folder("", root_id=self.folder_id)
            if not files:
                logger.warning("[JsonThemeDataLoader] 구글 드라이브 히트맵 폴더에 파일이 없습니다.")
                return

            drive_files_map = self._build_drive_files_map(files)
            if not drive_files_map:
                logger.info("[JsonThemeDataLoader] 동기화할 theme_*.json 파일이 드라이브에 없습니다.")
                return

            # 로컬 파일과 대조하여 최신본 동기화
            for name, drive_file in drive_files_map.items():
                local_file_path = local_dir / name
                drive_mtime = self._parse_drive_mtime(drive_file, name)
                await self._sync_single_file(name, drive_file, local_file_path, drive_mtime)

            # cleanup: 드라이브에 존재하지 않는 로컬 theme_*.json 파일 삭제
            self._cleanup_local_orphans(drive_files_map)

        except Exception as e:
            logger.error(f"[JsonThemeDataLoader] 히트맵 구글 드라이브 동기화 실패: {e}")

    def _build_drive_files_map(self, files: list[dict]) -> dict[str, dict]:
        """드라이브 파일 목록에서 유효한 theme_*.json 파일들의 맵을 정규화된 이름으로 구축합니다."""
        import unicodedata
        drive_files_map = {}
        for f in files:
            name_nfc = unicodedata.normalize("NFC", f["name"])
            if name_nfc.startswith("theme_") and name_nfc.endswith(".json"):
                drive_files_map[name_nfc] = f
        return drive_files_map

    def _parse_drive_mtime(self, drive_file: dict, name: str) -> float:
        """드라이브 파일 정보에서 수정 시각을 파싱하여 타임스탬프를 반환합니다."""
        drive_mtime = 0.0
        if "modifiedTime" in drive_file:
            try:
                from datetime import datetime
                drive_dt = datetime.fromisoformat(drive_file["modifiedTime"].replace("Z", "+00:00"))
                drive_mtime = drive_dt.timestamp()
            except Exception as ex:
                logger.warning(f"[JsonThemeDataLoader] 수정 시간 파싱 실패 ({name}): {ex}")
        return drive_mtime

    async def _sync_single_file(self, name: str, drive_file: dict, local_file_path: Any, drive_mtime: float) -> None:
        """단일 파일에 대해 필요 시 다운로드하고 동기화를 수행합니다."""
        need_download = True
        if local_file_path.exists() and drive_mtime > 0:
            local_mtime = os.path.getmtime(local_file_path)
            if (local_mtime - drive_mtime) >= -1.0:
                need_download = False

        if need_download:
            logger.info(f"[JsonThemeDataLoader] 히트맵 파일 다운로드 시작: {name}")
            data = await self.drive_adapter.get_file_by_id(drive_file["id"])
            if data:
                local_file_path.write_bytes(data)
                if drive_mtime > 0:
                    os.utime(local_file_path, (drive_mtime, drive_mtime))
                logger.info(f"[JsonThemeDataLoader] 히트맵 파일 동기화 성공: {name}")
            else:
                logger.error(f"[JsonThemeDataLoader] 히트맵 파일 다운로드 실패: {name}")
        else:
            logger.debug(f"[JsonThemeDataLoader] 로컬 파일이 최신 상태입니다: {name}")

    def _cleanup_local_orphans(self, drive_files_map: dict[str, dict]) -> None:
        """드라이브에 없는 로컬 theme_*.json 파일을 정리합니다."""
        from pathlib import Path
        local_files = glob.glob(os.path.join(self.json_dir, "theme_*.json"))
        for lf in local_files:
            lf_name = Path(lf).name
            if lf_name not in drive_files_map:
                try:
                    os.remove(lf)
                    logger.info(f"[JsonThemeDataLoader] 드라이브에 존재하지 않는 로컬 파일 삭제: {lf_name}")
                except Exception as ex:
                    logger.warning(f"[JsonThemeDataLoader] 로컬 파일 삭제 실패 ({lf_name}): {ex}")

    def load_heatmap(self) -> Heatmap:
        """지정된 로컬 디렉토리 내의 모든 theme_*.json 파일들을 파싱하여 계층형 Heatmap 도메인 모델을 반환합니다.

        Returns:
            파싱 완료된 전체 Heatmap 도메인 객체.
        """
        heatmap = Heatmap()

        json_pattern = os.path.join(self.json_dir, "theme_*.json")
        files = glob.glob(json_pattern)

        if not files:
            logger.warning(f"{self.json_dir} 경로에 theme_*.json 파일이 없습니다.")
            return heatmap

        for file_path in files:
            try:
                with open(file_path, encoding='utf-8') as f:
                    data = json.load(f)
                    self._parse_theme_file(data, heatmap)
            except Exception as e:
                logger.error(f"{file_path} 파싱 실패: {e}")

        return heatmap

    def _parse_theme_file(self, data: dict[str, Any], heatmap: Heatmap):
        """단일 테마 JSON 파일 데이터를 읽어 테마 및 카테고리 계층 구조를 생성하고 Heatmap에 추가합니다."""
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

    def _parse_sub_category_1(self, data: dict[str, Any], parent_category: Category, theme: Theme, seen_categories: set):
        """하위 카테고리 1단계 데이터를 파싱하여 상위 카테고리에 자식 요소로 등록합니다."""
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

    def _parse_sub_category_2(self, data: dict[str, Any], parent_category: Category, theme: Theme, seen_categories: set):
        """하위 카테고리 2단계 데이터를 파싱하여 상위 카테고리에 자식 요소로 등록합니다."""
        name = data.get('name', 'Unknown')

        if name in seen_categories:
            return
        seen_categories.add(name)

        category = Category(name=name)

        if 'companies' in data:
             self._add_companies(category, data['companies'], theme)

        parent_category.add_child(category)

    def _add_companies(self, category: Category, company_names: list[str], theme: Theme):
        """회사명 목록('이름:코드' 형식 지원)을 읽어 Stock 도메인 모델을 생성하고 카테고리 및 테마에 등록합니다."""
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
