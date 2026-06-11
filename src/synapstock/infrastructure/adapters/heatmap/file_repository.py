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
    
    def __init__(self, json_dir: str = 'data/heatmap', drive_adapter = None, folder_id: str | None = None):
        self.json_dir = json_dir
        self.drive_adapter = drive_adapter
        self.folder_id = folder_id

    async def sync_with_drive(self) -> None:
        """구글 드라이브 폴더로부터 theme_*.json 파일들을 로컬로 동기화(스마트 캐싱 적용)"""
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

            import unicodedata
            drive_files_map = {}
            for f in files:
                name_nfc = unicodedata.normalize("NFC", f["name"])
                if name_nfc.startswith("theme_") and name_nfc.endswith(".json"):
                    drive_files_map[name_nfc] = f

            if not drive_files_map:
                logger.info("[JsonThemeDataLoader] 동기화할 theme_*.json 파일이 드라이브에 없습니다.")
                return

            # 로컬 파일과 대조하여 최신본 동기화
            for name, drive_file in drive_files_map.items():
                local_file_path = local_dir / name
                
                # 드라이브 수정 시간 파싱
                drive_mtime = 0.0
                if "modifiedTime" in drive_file:
                    try:
                        from datetime import datetime
                        drive_dt = datetime.fromisoformat(drive_file["modifiedTime"].replace("Z", "+00:00"))
                        drive_mtime = drive_dt.timestamp()
                    except Exception as ex:
                        logger.warning(f"[JsonThemeDataLoader] 수정 시간 파싱 실패 ({name}): {ex}")

                # 스마트 캐싱 판단
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

            # cleanup: 드라이브에 존재하지 않는 로컬 theme_*.json 파일 삭제
            local_files = glob.glob(os.path.join(self.json_dir, "theme_*.json"))
            for lf in local_files:
                lf_name = Path(lf).name
                if lf_name not in drive_files_map:
                    try:
                        os.remove(lf)
                        logger.info(f"[JsonThemeDataLoader] 드라이브에 존재하지 않는 로컬 파일 삭제: {lf_name}")
                    except Exception as ex:
                        logger.warning(f"[JsonThemeDataLoader] 로컬 파일 삭제 실패 ({lf_name}): {ex}")

        except Exception as e:
            logger.error(f"[JsonThemeDataLoader] 히트맵 구글 드라이브 동기화 실패: {e}")

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
