import json
import logging
import os
import time
import unicodedata
from pathlib import Path
from typing import List, Optional, Dict

from synapstock.domain.models.report import Report
from synapstock.domain.ports import StoragePort

logger = logging.getLogger(__name__)

class ReportService:
    """리포트 관련 비즈니스 로직을 담당하는 애플리케이션 서비스.
    
    로컬 파일 시스템(data/report)과 클라우드 저장소(Google Drive) 사이의
    데이터 동기화 및 조회를 총괄한다.
    """

    def __init__(self, storage: StoragePort, report_folder_id: str, local_dir: str = "data/report"):
        self.storage = storage
        self.report_folder_id = report_folder_id
        self.local_dir = Path(local_dir)
        self.local_dir.mkdir(parents=True, exist_ok=True)
        self._last_sync_time = 0
        self._sync_interval = 300  # 5분

    def get_reports_by_stock(self, stock_name: str) -> List[Report]:
        """지정된 종목의 리포트 목록을 조회한다."""
        if not stock_name:
            return []

        # 자동 동기화 체크
        if time.time() - self._last_sync_time > self._sync_interval:
            self.sync_index()

        stock_nfc = unicodedata.normalize("NFC", stock_name)
        
        # 1. list.json (UI 최적화 인덱스) 우선 확인
        reports = self._load_from_list_json(stock_nfc)
        if reports:
            return reports

        # 2. reports.json (전문 인덱스) 확인
        reports = self._load_from_reports_json(stock_nfc)
        if reports:
            return reports

        # 3. 파일 시스템 스캔 폴백
        return self._scan_local_files(stock_nfc)

    def get_report_counts(self) -> Dict[str, int]:
        """종목별 리포트 수량을 집계한다."""
        counts = {}
        
        # 인덱스 파일 기반 집계 시도
        list_path = self.local_dir / "list.json"
        if list_path.exists():
            try:
                with open(list_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for r in data:
                        filename = r.get("filename", "")
                        if "[" in filename and "]" in filename:
                            stock = filename.split("[")[1].split("]")[0]
                            counts[stock] = counts.get(stock, 0) + 1
                return counts
            except Exception:
                pass

        # 폴백: 파일 시스템 직접 스캔
        for f in self.local_dir.glob("*.pdf"):
            filename = unicodedata.normalize("NFC", f.name)
            if "[" in filename and "]" in filename:
                try:
                    stock = filename.split("[")[1].split("]")[0]
                    counts[stock] = counts.get(stock, 0) + 1
                except Exception:
                    pass
        return counts

    def sync_index(self) -> List[str]:
        """Google Drive에서 인덱스 파일들을 강제로 동기화한다."""
        updated = []
        try:
            # 1. list.json 동기화
            list_data = self.storage.get_file("list.json", folder="report")
            if list_data:
                with open(self.local_dir / "list.json", "wb") as f:
                    f.write(list_data)
                updated.append("list.json")

            # 2. reports.json 동기화
            reports_data = self.storage.get_file("reports.json", folder="report")
            if reports_data:
                with open(self.local_dir / "reports.json", "wb") as f:
                    f.write(reports_data)
                updated.append("reports.json")

            self._last_sync_time = time.time()
            if updated:
                logger.info(f"[ReportService] 인덱스 동기화 완료: {', '.join(updated)}")
        except Exception as e:
            logger.error(f"[ReportService] 동기화 중 오류 발생: {e}")
        
        return updated

    def get_file_content_path(self, filename: str) -> Optional[Path]:
        """파일의 로컬 경로를 반환한다. 로컬에 없으면 클라우드에서 다운로드한다."""
        safe_filename = os.path.basename(filename)
        if not safe_filename.lower().endswith(".pdf"):
            return None

        local_path = self.local_dir / safe_filename
        if local_path.exists():
            return local_path

        # 온디맨드 다운로드
        logger.info(f"[ReportService] 클라우드에서 파일 다운로드 시도: {safe_filename}")
        if self.storage.download_file(safe_filename, str(local_path), folder="report"):
            return local_path

        return None

    def _load_from_list_json(self, stock_nfc: str) -> List[Report]:
        list_path = self.local_dir / "list.json"
        if not list_path.exists():
            return []
            
        try:
            with open(list_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                results = []
                for r in data:
                    f_name = r["filename"]
                    if "[" in f_name and "]" in f_name:
                        try:
                            f_stock = f_name.split("[")[1].split("]")[0]
                            if f_stock == stock_nfc:
                                results.append(Report(
                                    filename=f_name,
                                    stock=f_stock,
                                    title=f_name,
                                    date=r["date"],
                                    provider="Unknown",
                                    url=f"/report_files/{f_name}"
                                ))
                        except Exception: continue
                return sorted(results, key=lambda x: x.date, reverse=True)
        except Exception as e:
            logger.error(f"Error loading list.json: {e}")
            return []

    def _load_from_reports_json(self, stock_nfc: str) -> List[Report]:
        index_path = self.local_dir / "reports.json"
        if not index_path.exists():
            return []
            
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                reports_data = data.get("reports", [])
                results = []
                for r in reports_data:
                    if unicodedata.normalize("NFC", r["stock"]) == stock_nfc:
                        results.append(Report(
                            filename=r["filename"],
                            stock=r["stock"],
                            title=r["title"],
                            date=r["date"],
                            provider=r["provider"],
                            url=f"/report_files/{r['filename']}"
                        ))
                return sorted(results, key=lambda x: x.date, reverse=True)
        except Exception as e:
            logger.error(f"Error loading reports.json: {e}")
            return []

    def _scan_local_files(self, stock_nfc: str) -> List[Report]:
        results = []
        search_patterns = [f"[{stock_nfc}]", stock_nfc]
        for f in self.local_dir.glob("*.pdf"):
            filename_nfc = unicodedata.normalize("NFC", f.name)
            if any(p in filename_nfc for p in search_patterns):
                results.append(Report(
                    filename=f.name,
                    stock=stock_nfc,
                    title=f.name,
                    date="Unknown",
                    provider="Manual",
                    url=f"/report_files/{f.name}"
                ))
        return sorted(results, key=lambda x: x.filename, reverse=True)
