"""리포트 인덱스 동기화 및 파일 서빙 API 라우터.

로컬 인덱스(``list.json``, ``reports.json``) 조회, Google Drive 강제 동기화,
PDF 파일 온디맨드 다운로드 및 서빙 엔드포인트를 제공합니다.
"""
import json
import os
import unicodedata
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

from fastapi.responses import JSONResponse

from fastapi import APIRouter

from synapstock.presentation.web.core.dependencies import drive_adapter, sync_indices_if_needed

router = APIRouter()


@router.get("/api/reports/local")
async def get_local_reports(name: str):
    """지정된 종목명이 포함된 리포트 목록을 반환합니다.

    Args:
        name (str): 조회할 종목명 (NFC 정규화 후 비교).

    Returns:
        list[dict]: 리포트 목록. 각 항목은 다음 키를 포함합니다:
            - ``filename`` (str): 파일명.
            - ``url`` (str): 리포트 파일에 접근할 수 있는 URL.
            - ``date`` (str): ``YYYY-MM-DD`` 형식의 날짜.
            - ``provider`` (str): 리포트 제공사(증권사).
            - ``title`` (str): 리포트 제목.

    Note:
        조회 시 Google Drive 인덱스를 5분 주기로 자동 동기화합니다.
        ``list.json`` → ``reports.json`` → 파일 시스템 스캔 순으로 폴백합니다.

    Raises:
        JSONResponse (500): 조회 중 예외 발생 시.
    """
    try:
        if not name:
            return []

        if drive_adapter:
            await sync_indices_if_needed()

        name_nfc = unicodedata.normalize("NFC", name)

        # 1. UI 전용 인덱스 (list.json) 확인
        list_path = Path("data/report/list.json")
        if list_path.exists():
            with open(list_path, "r", encoding="utf-8") as f:
                reports = json.load(f)
                results = []
                for r in reports:
                    f_name = r["filename"]
                    filename_stock = ""
                    if "[" in f_name and "]" in f_name:
                        try:
                            filename_stock = f_name.split("[")[1].split("]")[0]
                        except Exception:
                            pass

                    if filename_stock == name_nfc:
                        results.append(
                            {
                                "filename": f_name,
                                "url": f"/report_files/{f_name}",
                                "date": r["date"],
                                "provider": "Unknown",
                                "title": f_name,
                            }
                        )
                if results:
                    results.sort(key=lambda x: x["date"], reverse=True)
                    return results

        # 2. 전문 인덱스 (reports.json) 확인
        index_path = Path("data/report/reports.json")
        if index_path.exists():
            with open(index_path, "r", encoding="utf-8") as f:
                index_data = json.load(f)
                reports = index_data.get("reports", [])

                results = []
                for r in reports:
                    r_name = unicodedata.normalize("NFC", r["stock"])
                    if r_name == name_nfc:
                        results.append(
                            {
                                "filename": r["filename"],
                                "url": f"/report_files/{r['filename']}",
                                "date": r["date"],
                                "provider": r["provider"],
                                "title": r["title"],
                            }
                        )
                results.sort(key=lambda x: x["date"], reverse=True)
                return results

        # 3. 인덱스 없으면 파일 시스템 스캔
        report_path = Path("data/report")
        if not report_path.exists():
            return []

        results = []
        search_patterns = [f"[{name_nfc}]", name_nfc]
        for f in report_path.glob("*.pdf"):
            filename_nfc = unicodedata.normalize("NFC", f.name)
            if any(p in filename_nfc for p in search_patterns):
                results.append({"filename": f.name, "url": f"/report_files/{f.name}"})
        results.sort(key=lambda x: x["filename"], reverse=True)
        return results
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})


@router.get("/api/reports/counts")
async def get_report_counts():
    """전체 종목별 리포트 수량을 집계하여 반환합니다.

    ``list.json``이 있으면 인덱스 기반으로, 없으면 파일 시스템 스캔으로 폴백합니다.

    Returns:
        dict[str, int]: 종목명을 키로 하는 리포트 수량 딕셔너리.
            예: ``{"삼성전자": 5, "SK하이닉스": 3}``.

    Raises:
        JSONResponse (500): 집계 중 예외 발생 시.
    """
    try:
        if drive_adapter:
            await sync_indices_if_needed()

        counts = {}

        # 1. UI 전용 인덱스 (list.json) 사용
        list_path = Path("data/report/list.json")
        if list_path.exists():
            with open(list_path, "r", encoding="utf-8") as f:
                reports = json.load(f)
                for r in reports:
                    filename = r.get("filename", "")
                    if "[" in filename and "]" in filename:
                        try:
                            stock_name = filename.split("[")[1].split("]")[0]
                            counts[stock_name] = counts.get(stock_name, 0) + 1
                        except Exception:
                            pass
            return counts

        # 2. 파일 시스템 스캔 폴백
        report_path = Path("data/report")
        if not report_path.exists():
            return {}

        for f in report_path.glob("*.pdf"):
            filename = unicodedata.normalize("NFC", f.name)
            if "[" in filename and "]" in filename:
                try:
                    parts = filename.split("[")
                    if len(parts) > 1:
                        stock_name = parts[1].split("]")[0]
                        counts[stock_name] = counts.get(stock_name, 0) + 1
                except Exception:
                    pass
        return counts
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})


@router.post("/api/reports/sync")
async def sync_reports_index():
    """Google Drive에서 최신 인덱스 파일을 강제로 동기화합니다.

    ``list.json``과 ``reports.json`` 두 파일을 모두 업데이트합니다.
    ``drive_adapter``가 설정되지 않은 경우 400 오류를 반환합니다.

    Returns:
        dict: 성공 시 ``{"status": "success", "message": str}``,
            파일이 없을 경우 ``{"status": "error", "message": str}``.

    Raises:
        JSONResponse (400): Google Drive 어댑터가 설정되지 않은 경우.
        JSONResponse (500): 동기화 중 예외 발생 시.
    """
    if not drive_adapter:
        return JSONResponse(status_code=400, content={"message": "Cloud sync not configured"})

    try:
        updated = []
        list_data = drive_adapter.get_file("list.json")
        if list_data:
            with open("data/report/list.json", "wb") as f:
                f.write(list_data)
            updated.append("list.json")

        reports_data = drive_adapter.get_file("reports.json")
        if reports_data:
            with open("data/report/reports.json", "wb") as f:
                f.write(reports_data)
            updated.append("reports.json")

        if updated:
            return {"status": "success", "message": f"Updated from cloud: {', '.join(updated)}"}
        return {"status": "error", "message": "Index files not found in cloud"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})


@router.get("/report_files/{filename}")
async def serve_report_file(filename: str):
    """PDF 리포트 파일을 서빙합니다.

    로컬에 파일이 있으면 즉시 반환하고, 없으면 Google Drive에서 온디맨드
    다운로드를 시도한 뒤 로컬에 저장하여 반환합니다.

    Args:
        filename (str): 요청한 PDF 파일명. 경로 트래버설 방지를 위해
            ``os.path.basename`` 처리를 적용합니다.

    Returns:
        FileResponse: 로컬 PDF 파일 응답.

    Raises:
        JSONResponse (400): ``.pdf`` 확장자가 아닌 경우.
        JSONResponse (404): 로컬 및 클라우드 모두에서 파일을 찾지 못한 경우.
    """
    from fastapi.responses import FileResponse

    safe_filename = os.path.basename(filename)
    if not safe_filename.lower().endswith(".pdf"):
        return JSONResponse(status_code=400, content={"message": "Invalid file type"})

    local_path = Path("data/report") / safe_filename

    if local_path.exists():
        return FileResponse(local_path)

    if drive_adapter:
        logger.info(f"[CLOUD] 파일 다운로드 시도 중: {filename}")
        if drive_adapter.download_file(filename, local_path):
            return FileResponse(local_path)

    return JSONResponse(status_code=404, content={"message": "File not found locally or in cloud"})
