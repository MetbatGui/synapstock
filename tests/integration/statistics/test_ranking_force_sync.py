import io
import logging
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest

from synapstock.application.services.ranking_service import RankingService
from synapstock.domain.statistics.models import MarketType, SupplySubject
from synapstock.infrastructure.adapters.local.cache_manager import LocalCacheManager

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@pytest.fixture
def mock_drive_adapter():
    adapter = AsyncMock()
    
    # 1. 폴더 목록 모킹
    adapter.list_files_in_folder.side_effect = [
        [{"id": "year_folder_id", "name": "2026년"}],  # 연도 폴더 찾기
        [{"id": "sub_folder_id", "name": "일별수급정리표"}],  # 서브 폴더 찾기
        [{"id": "file_id", "name": "2026일별수급순위정리표.xlsx", "modifiedTime": "2026-04-29T10:00:00Z"}]  # 대상 파일 찾기
    ]
    
    # 2. 파일 다운로드 모킹 (파서가 기대하는 레이아웃으로 생성)
    output = io.BytesIO()
    # 20개 이상의 컬럼을 가진 더미 데이터프레임 생성
    data = [["-"] * 20 for _ in range(40)]
    # KOSPI FOREIGN (4번, 5번 컬럼), 4행(0-indexed)부터
    data[4][4] = "삼성전자"
    data[4][5] = 1000
    
    df = pd.DataFrame(data)
    with pd.ExcelWriter(output) as writer:
        df.to_excel(writer, sheet_name="0429", index=False, header=False)
    
    adapter.get_file_by_id.return_value = output.getvalue()
    
    return adapter

@pytest.fixture
def mock_repository():
    repo = MagicMock()
    repo.list_available_dates.return_value = ["2026-04-29"]
    repo.load_ranking.return_value = None
    repo.get_rankings.return_value = []
    return repo

@pytest.mark.asyncio
async def test_ranking_force_sync_when_modified_time_changes(mock_drive_adapter, mock_repository):
    """파일 수정 시간이 변경되었을 때 기존 데이터가 있더라도 강제 동기화되는지 테스트."""
    
    # 임시 캐시 파일 사용
    import os
    import tempfile
    import json
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False, encoding="utf-8") as tmp:
        json.dump({}, tmp)
        manifest_path = tmp.name
    
    try:
        cache_manager = LocalCacheManager(manifest_path=manifest_path)
        # 초기 상태: 10:00:00Z로 저장
        cache_manager.update_cache_info("ranking", "2026일별수급순위정리표.xlsx", "2026-04-29T10:00:00Z")
        
        service = RankingService(mock_drive_adapter, "dummy_folder", mock_repository)
        service.cache_manager = cache_manager # 수동 주입
        
        # 1. 동일한 시간일 때는 동기화 건너뜀 (기존 로직 유지 확인)
        logger.info("--- 동일한 수정 시간 테스트 ---")
        res1 = await service.sync_data("2026-04-29")
        # existing_dates에 2026-04-29가 있으므로 newly_synced_count는 0이어야 함
        assert len(res1) == 0 # 새로 동기화된 데이터 없음
        
        # 2. 수정 시간이 변경된 경우 (11:00:00Z)
        logger.info("--- 변경된 수정 시간 테스트 (기존 데이터 존재) ---")
        mock_drive_adapter.list_files_in_folder.side_effect = [
            [{"id": "year_folder_id", "name": "2026년"}],
            [{"id": "sub_folder_id", "name": "일별수급정리표"}],
            [{"id": "file_id", "name": "2026일별수급순위정리표.xlsx", "modifiedTime": "2026-04-29T11:00:00Z"}]
        ]
        
        res2 = await service.sync_data("2026-04-29")
        
        # 로직 변경 후: 수정 시간이 다르더라도 existing_dates에 2026-04-29가 있으므로 newly_synced_count는 0
        # 하지만 needs_sync가 True였으므로 cache_manager는 업데이트되어야 함
        assert len(res2) == 0 or (hasattr(res2, "items") and len(res2.items) == 0) # 새로 추가된 랭킹 리스트는 비어있음
        
        # 캐시 매니페스트에 새로운 시간 저장 확인
        assert cache_manager.cache["ranking:2026일별수급순위정리표.xlsx"]["modified_time"] == "2026-04-29T11:00:00Z"
        
        # 3. 새로운 시트가 추가된 경우 테스트
        logger.info("--- 새로운 시트 추가 테스트 ---")
        mock_drive_adapter.list_files_in_folder.side_effect = [
            [{"id": "year_folder_id", "name": "2026년"}],
            [{"id": "sub_folder_id", "name": "일별수급정리표"}],
            [{"id": "file_id", "name": "2026일별수급순위정리표.xlsx", "modifiedTime": "2026-04-29T12:00:00Z"}]
        ]
        
        # 새로운 시트(0430)가 포함된 엑셀 모킹
        output = io.BytesIO()
        data = [["-"] * 20 for _ in range(40)]
        data[4][4] = "현대차"
        data[4][5] = 2000
        df = pd.DataFrame(data)
        with pd.ExcelWriter(output) as writer:
            df.to_excel(writer, sheet_name="0429", index=False, header=False)
            df.to_excel(writer, sheet_name="0430", index=False, header=False)
        mock_drive_adapter.get_file_by_id.return_value = output.getvalue()
        
        res3 = await service.sync_data("2026-04-30")
        
        # 0429는 건너뛰고 0430만 파싱되어야 함 (newly_synced_count = 1)
        assert len(res3) > 0
        assert res3[0].date == "2026-04-30"
        assert res3[0].items[0].name == "현대차"
        
    finally:
        if os.path.exists(manifest_path):
            os.remove(manifest_path)

if __name__ == "__main__":
    pytest.main([__file__])
