import pytest
import pandas as pd
import json
from pathlib import Path

from evenezer.infrastructure.adapters.local.stock_split_repo import LocalStockSplitRepository
from evenezer.domain.statistics.models import StockSplitManifest, StockSplit


def test_load_manifest_not_exists(tmp_path):
    """매니페스트가 존재하지 않을 때 None을 반환하는지 확인."""
    repo = LocalStockSplitRepository(data_root=str(tmp_path))
    assert repo.load_manifest() is None


def test_save_and_load_manifest(tmp_path):
    """매니페스트를 저장하고 다시 정상적으로 로드하는지 확인."""
    repo = LocalStockSplitRepository(data_root=str(tmp_path))
    
    manifest_data = StockSplitManifest(
        manifest_version="1.0.0",
        last_updated="2026-05-27T14:21:56.077970",
        total_records=2,
        supported_years=["2024", "2025"],
        years_index={"2024": ["20241212801081"], "2025": ["20251229900244"]}
    )
    
    repo.save_manifest(manifest_data)
    
    loaded = repo.load_manifest()
    assert loaded is not None
    assert loaded.manifest_version == "1.0.0"
    assert loaded.total_records == 2
    assert "2024" in loaded.years_index
    assert loaded.supported_years == ["2024", "2025"]


def test_save_excel_and_mtime(tmp_path):
    """엑셀 파일을 저장하고 수정 시간(mtime)을 올바르게 구하는지 확인."""
    repo = LocalStockSplitRepository(data_root=str(tmp_path))
    filename = "액면분할(2024년).xlsx"
    content = b"fake excel content"
    
    repo.save_excel_file(filename, content)
    
    file_path = tmp_path / filename
    assert file_path.exists()
    assert file_path.read_bytes() == content
    
    mtime = repo.get_file_mtime(filename)
    assert mtime is not None
    assert mtime > 0
    
    # 존재하지 않는 파일의 mtime은 None
    assert repo.get_file_mtime("not_exists.xlsx") is None


def test_load_by_year_with_pandas_excel(tmp_path):
    """실제 엑셀 형식 데이터를 임시 생성하여 정상 파싱 및 엣지 케이스 정규화 확인."""
    repo = LocalStockSplitRepository(data_root=str(tmp_path))
    
    # 1. 2024년 엑셀 데이터 모형 생성
    df_data = {
        "회사명": ["삼성전자", "엣지컴퍼니", float("nan"), "정상기업"],
        "시장": ["KOSPI", float("nan"), "KOSDAQ", "KOSDAQ"],
        "공시구분": ["공시", "nan", "공시", None],
        "배정기준일": ["2024.12.12", "2024.12.20", "2024-01-01", "2024.05.05"],
        "이사회결의일": ["2024.12.12 00:00:00", "NaN", None, "2024.05.01"],
        "접수번호": ["20241212801081", "20241220901234", "20240101800111", "2.0240505e+13"],
        "원접수번호": [None, None, None, None],
        "발행주식수(이전)": ["20520649.0", None, 1000, 500000],
        "발행주식수(이후)": [102603245, "NaN", 5000, 1000000],
        "분할비율": [5.0, None, 5, 2.0],
        "신주상장예정일": ["2025-02-27", None, "2024-02-15", None],
        "주총결의일": ["2024-12-12", None, None, "2024.05.02"]
    }
    
    df = pd.DataFrame(df_data)
    file_path = tmp_path / "액면분할(2024년).xlsx"
    
    # 임시 엑셀 저장
    df.to_excel(file_path, sheet_name="주식분할_2024년", index=False)
    
    # 2. 로드 테스트 실행
    splits = repo.load_by_year("2024")
    
    # 4개 행 중 3번째 행(회사명이 NaN)은 누락 스킵되어 총 3개의 주식분할 객체가 파싱되어야 함
    assert len(splits) == 3
    
    # 1번째 회사: 삼성전자 검증
    s1 = next(x for x in splits if x.company_name == "삼성전자")
    assert s1.market == "KOSPI"
    assert s1.base_date == "2024-12-12"
    assert s1.board_resolution_date == "2024-12-12"  # 시간 제거 확인
    assert s1.receipt_no == "20241212801081"
    assert s1.prev_shares == 20520649
    assert s1.split_ratio == 5.0
    
    # 2번째 회사: 엣지컴퍼니 검증 (NaN 및 결측 데이터들)
    s2 = next(x for x in splits if x.company_name == "엣지컴퍼니")
    assert s2.market is None
    assert s2.disclosure_type is None
    assert s2.board_resolution_date is None
    assert s2.post_shares is None
    assert s2.split_ratio is None
    
    # 3번째 회사: 정상기업 검증 (지수식 접수번호)
    s3 = next(x for x in splits if x.company_name == "정상기업")
    assert s3.receipt_no == "20240505000000" or "20240505" in s3.receipt_no


def test_load_all_sorting_and_manifest_fallback(tmp_path):
    """load_all()이 연도별 파일들을 합쳐 배정기준일 최신순으로 정렬하는지 확인."""
    repo = LocalStockSplitRepository(data_root=str(tmp_path))
    
    # 2024년 데이터 생성 (이전 날짜)
    df2024 = pd.DataFrame({
        "회사명": ["옛날회사"], "배정기준일": ["2024.12.12"], "접수번호": ["20241212801081"]
    })
    df2024.to_excel(tmp_path / "액면분할(2024년).xlsx", sheet_name="주식분할_2024년", index=False)
    
    # 2025년 데이터 생성 (최신 날짜)
    df2025 = pd.DataFrame({
        "회사명": ["최신회사"], "배정기준일": ["2025.05.05"], "접수번호": ["20250505801234"]
    })
    df2025.to_excel(tmp_path / "액면분할(2025년).xlsx", sheet_name="주식분할_2025년", index=False)
    
    # load_all 호출 (매니페스트 없는 경우의 fallback 테스트도 자동 포함됨)
    all_splits = repo.load_all()
    
    assert len(all_splits) == 2
    # 배정기준일 기준 정렬 확인: 최신일자 2025.05.05 가 맨 앞에 위치해야 함
    assert all_splits[0].company_name == "최신회사"
    assert all_splits[0].base_date == "2025-05-05"
    assert all_splits[1].company_name == "옛날회사"
