import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import pandas as pd
import io
import json
from datetime import datetime

from evenezer.application.services.weekly_change_service import WeeklyChangeService
from evenezer.domain.statistics.models import WeeklyChangeReport, WeeklyChangeItem


@pytest.fixture
def mock_drive():
    """비동기 드라이브 어댑터의 모의 객체를 생성합니다."""
    drive = MagicMock()
    drive.get_file = AsyncMock()
    drive.list_files_in_folder = AsyncMock()
    return drive


@pytest.fixture
def mock_repo():
    """로컬 리포지토리의 모의 객체를 생성합니다."""
    repo = MagicMock()
    return repo


@pytest.fixture
def weekly_change_service(mock_drive, mock_repo):
    """모의 객체들이 주입된 WeeklyChangeService 인스턴스를 생성합니다."""
    return WeeklyChangeService(drive_adapter=mock_drive, folder_id="folder_123", repository=mock_repo)


def create_mock_excel_bytes():
    """WeeklyChangeParser가 정상 파싱할 수 있는 컬럼명을 포함한 모의 엑셀 바이트를 생성합니다."""
    df = pd.DataFrame([
        {"종목명": "삼성전자", "종목코드": "005930", "종가": 70000, "기준가": 68000, "등락률": 2.94},
        {"종목명": "SK하이닉스", "종목코드": "000660", "종가": 180000, "기준가": 175000, "등락률": "2.86%"},
        {"종목명": "nan", "종목코드": "NaN", "종가": None, "기준가": None, "등락률": None}  # 예외 분기 (파서에서 continue 처리됨)
    ])
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    return out.getvalue()


# -----------------------------------------------------------------------------
# WeeklyChangeService Tests
# -----------------------------------------------------------------------------

def test_weekly_change_service_init(mock_drive, mock_repo):
    """WeeklyChangeService 초기화 시 필드들이 정상 할당되는지 검증합니다."""
    service = WeeklyChangeService(drive_adapter=mock_drive, folder_id="folder_123", repository=mock_repo)

    assert service.drive_adapter == mock_drive
    assert service.folder_id == "folder_123"
    assert service.repository == mock_repo
    assert service.get_service_name() == "WeeklyChangeService"


@pytest.mark.asyncio
async def test_get_weekly_change_from_local_cache(weekly_change_service, mock_drive, mock_repo):
    """force_sync=False 상태에서 로컬 캐시(repository)에 리포트가 존재할 시 즉시 캐시를 리턴하는지 검증합니다."""
    mock_report = WeeklyChangeReport(date="2026-05-08", year=2026, month=5, week_of_month=1, week_num=19, date_range="0504~0508", items=[])
    mock_repo.load_report.return_value = mock_report

    result = await weekly_change_service.get_weekly_change(date="2026-05-08", force_sync=False)
    
    assert result == mock_report
    mock_repo.load_report.assert_called_once_with("2026-05-08")
    mock_drive.get_file.assert_not_called()


@pytest.mark.asyncio
async def test_get_weekly_change_sync_trigger(weekly_change_service, mock_repo):
    """로컬 캐시가 없거나 force_sync=True 일 때 sync_data가 정상 호출되는지 검증합니다."""
    # load_report 가 None을 반환하도록 설정
    mock_repo.load_report.return_value = None

    with patch.object(weekly_change_service, "sync_data") as mock_sync:
        mock_sync.return_value = MagicMock()
        await weekly_change_service.get_weekly_change(date="2026-05-08", force_sync=False)
        mock_sync.assert_called_once_with("2026-05-08")


@pytest.mark.asyncio
async def test_load_manifest_cases(weekly_change_service, mock_drive, mock_repo):
    """_load_manifest의 성공, 어댑터 없음, JSON 예외 등의 상황을 검증합니다."""
    # 1. drive_adapter가 None일 때 None 리턴
    service_no_drive = WeeklyChangeService(drive_adapter=None, folder_id="f", repository=mock_repo)
    assert await service_no_drive._load_manifest() is None

    # 2. 정상 로드 및 파싱 성공
    manifest_data = {"event_1": {"year": 2026}}
    mock_drive.get_file.return_value = json.dumps(manifest_data).encode("utf-8")
    
    result = await weekly_change_service._load_manifest()
    assert result == manifest_data
    mock_drive.get_file.assert_called_once_with("event_manifest.json", folder="weekly_change")

    # 3. 디코딩/파싱 예외 발생 시 None 리턴
    mock_drive.get_file.side_effect = Exception("File load failed")
    assert await weekly_change_service._load_manifest() is None


def test_get_full_week_range():
    """연도와 주차 정보를 입력받아 ISO 규격 기반 해당 주 범위(MMDD~MMDD)를 올바르게 계산하는지 검증합니다."""
    service = WeeklyChangeService(None, "f", None)
    
    # 2026년 19주차 월요일은 5월 4일, 금요일은 5월 8일
    week_range = service._get_full_week_range(2026, 19)
    assert week_range == "0504~0508"


@pytest.mark.asyncio
async def test_sync_data_no_adapter(mock_repo):
    """sync_data 호출 시 drive_adapter가 없으면 조기 리턴되는지 확인합니다."""
    service = WeeklyChangeService(drive_adapter=None, folder_id="f", repository=mock_repo)
    assert await service.sync_data("2026-05-08") is None


@pytest.mark.asyncio
async def test_sync_data_manifest_match_success(weekly_change_service, mock_drive, mock_repo):
    """매니페스트에서 대상 일자에 매칭되는 이벤트를 발견하여 정규식 보정 경로로 파일을 받아 파싱/저장하는 흐름을 검증합니다."""
    manifest_mock = {
        "event_19": {
            "year": 2026,
            "month": 5,
            "week": 19,
            "status": "COMPLETED",
            "last_trading_day": "2026-05-08",
            "filename": "weekly_gainers_2026_W19_05M1W_9999~9999.xlsx"  # 보정될 파일명
        }
    }

    excel_bytes = create_mock_excel_bytes()

    with patch.object(weekly_change_service, "_load_manifest", return_value=manifest_mock):
        mock_drive.get_file.return_value = excel_bytes
        
        report = await weekly_change_service.sync_data("2026-05-08")
        
        # 1. 리포트 생성 및 데이터 검증
        assert isinstance(report, WeeklyChangeReport)
        assert report.date == "2026-05-08"
        assert report.year == 2026
        assert len(report.items) == 2  # 삼성전자, SK하이닉스 파싱
        assert report.items[0].name == "삼성전자"
        assert report.items[0].change_rate == 2.94

        # 2. 파일명 보정(MMDD~MMDD) 및 핀포인트 다운로드 확인
        expected_path = "2026/05월/weekly_gainers_2026_W19_05M1W_0504~0508.xlsx"
        mock_drive.get_file.assert_called_once_with(expected_path, folder="weekly_change")
        
        # 3. DB 저장 확인
        mock_repo.save_report.assert_called_once_with(report)


@pytest.mark.asyncio
async def test_sync_data_manifest_fallback_latest(weekly_change_service, mock_drive, mock_repo):
    """date_str을 지정하지 않았을 때 완료된 최신 이벤트를 탐색하여 동기화하는지 검증합니다."""
    # 18주차와 19주차 완료 이벤트가 있을 때 19주차가 선택되어야 함
    manifest_mock = {
        "event_18": {
            "year": 2026,
            "month": 4,
            "week": 18,
            "status": "COMPLETED",
            "last_trading_day": "2026-05-01",
            "filename": "weekly_gainers_2026_W18_04M4W_0427~0501.xlsx"
        },
        "event_19": {
            "year": 2026,
            "month": 5,
            "week": 19,
            "status": "COMPLETED",
            "last_trading_day": "2026-05-08",
            "filename": "weekly_gainers_2026_W19_05M1W_0504~0508.xlsx"
        }
    }

    excel_bytes = create_mock_excel_bytes()

    with patch.object(weekly_change_service, "_load_manifest", return_value=manifest_mock):
        mock_drive.get_file.return_value = excel_bytes
        
        report = await weekly_change_service.sync_data(date_str=None)
        
        assert report.date == "2026-05-08"
        mock_drive.get_file.assert_called_once_with("2026/05월/weekly_gainers_2026_W19_05M1W_0504~0508.xlsx", folder="weekly_change")


@pytest.mark.asyncio
async def test_sync_data_fallback_scanned_files_success(weekly_change_service, mock_drive, mock_repo):
    """매니페스트를 통한 동기화 시도가 매칭 실패 시, 드라이브 탐색 폴백을 통해 최신 엑셀을 로드하는지 확인합니다."""
    excel_bytes = create_mock_excel_bytes()

    with patch.object(weekly_change_service, "_load_manifest", return_value={}):
        # 폴백 시도 시 list_files_in_folder 모의 응답
        # 1순위: date_str에 매칭되는 연도/월 폴더 검색
        # 2순위: 전체 루트 검색
        mock_drive.list_files_in_folder.side_effect = [
            # 2026/05월 폴더 내 파일 목록
            [{"name": "weekly_gainers_2026_W19_05M1W_0504~0508.xlsx"}],
            []
        ]
        mock_drive.get_file.return_value = excel_bytes

        report = await weekly_change_service.sync_data(date_str="2026-05-08")
        
        assert report.date == "2026-05-08"
        mock_drive.list_files_in_folder.assert_any_call("2026/05월", folder="weekly_change")
        # 최신 파일 다운로드 수행 확인
        mock_drive.get_file.assert_called_once_with("weekly_gainers_2026_W19_05M1W_0504~0508.xlsx", folder="weekly_change")
        mock_repo.save_report.assert_called_once()


@pytest.mark.asyncio
async def test_sync_data_fallback_no_files(weekly_change_service, mock_drive):
    """폴백 탐색을 하였으나 조건에 매칭되는 파일이 없는 경우 None을 리턴하는지 테스트합니다."""
    with patch.object(weekly_change_service, "_load_manifest", return_value={}):
        mock_drive.list_files_in_folder.return_value = [] # 스캔 결과 없음
        
        report = await weekly_change_service.sync_data(date_str="2026-05-08")
        assert report is None


@pytest.mark.asyncio
async def test_sync_data_fallback_get_file_fail(weekly_change_service, mock_drive):
    """폴백 스캔을 통해 최신 엑셀 파일명은 찾았으나 파일 다운로드에 실패했을 때 None을 반환하는지 검증합니다."""
    with patch.object(weekly_change_service, "_load_manifest", return_value={}):
        mock_drive.list_files_in_folder.return_value = [{"name": "weekly_gainers_2026_W19_05M1W_0504~0508.xlsx"}]
        mock_drive.get_file.return_value = None # 다운로드 실패
        
        report = await weekly_change_service.sync_data(date_str="2026-05-08")
        assert report is None


@pytest.mark.asyncio
async def test_list_available_dates_merge_success(weekly_change_service, mock_drive, mock_repo):
    """로컬 가용 날짜 목록과 매니페스트를 통한 클라우드 날짜 목록이 정상 병합 및 내림차순 정렬되는지 검증합니다."""
    # 1. 로컬 날짜 목록 설정
    mock_repo.list_available_dates.return_value = ["2026-05-01"]
    local_report = WeeklyChangeReport(
        date="2026-05-01", year=2026, month=5, week_of_month=1, week_num=18, date_range="0427~0501", items=[]
    )
    mock_repo.load_report.return_value = local_report

    # 2. 매니페스트 (클라우드) 날짜 설정 (로컬에 없는 새로운 2026-05-08 주차 완료 기록)
    manifest_mock = {
        "event_19": {
            "year": 2026,
            "month": 5,
            "week_of_month": 2,
            "week": 19,
            "status": "COMPLETED",
            "last_trading_day": "2026-05-08",
            "filename": "weekly_gainers_2026_W19_05M2W_0504~0508.xlsx"
        },
        "event_unfinished": {
            "status": "RUNNING", # 제외되어야 함
            "last_trading_day": "2026-05-15"
        }
    }

    with patch.object(weekly_change_service, "_load_manifest", return_value=manifest_mock):
        results = await weekly_change_service.list_available_dates()
        
        assert len(results) == 2
        # 내림차순 정렬 확인 (05-08이 첫번째)
        assert results[0]["date"] == "2026-05-08"
        assert results[0]["source"] == "cloud"
        
        assert results[1]["date"] == "2026-05-01"
        assert results[1]["source"] == "local"


@pytest.mark.asyncio
async def test_list_available_dates_fallback_scan_success(weekly_change_service, mock_drive, mock_repo):
    """매니페스트가 설정되지 않았을 때 제한적 클라우드 디렉터리 스캔을 통해 날짜 메타데이터를 유도하는지 확인합니다."""
    mock_repo.list_available_dates.return_value = []
    
    with patch.object(weekly_change_service, "_load_manifest", return_value=None):
        # 현재 연도 폴더의 파일 목록 스캔 반환
        mock_drive.list_files_in_folder.return_value = [
            {"name": "weekly_gainers_2026_W19_05M1W_0504~0508.xlsx"},
            {"name": "~$temporary_file.xlsx"}, # 무시되어야 함
            {"name": "weekly_gainers_2026_W20_05M2W_Unknown.xlsx"} # Unknown 무시되어야 함
        ]
        
        results = await weekly_change_service.list_available_dates()
        
        assert len(results) == 1
        assert results[0]["date"] == "2026-05-08"
        assert results[0]["week_num"] == 19
        assert results[0]["source"] == "cloud"

