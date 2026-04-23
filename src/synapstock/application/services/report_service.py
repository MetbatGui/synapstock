import json
import logging
import time
import unicodedata
from pathlib import Path

from synapstock.domain.models import Report
from synapstock.domain.ports import StoragePort

logger = logging.getLogger(__name__)


class ReportService:
    """리포트 관련 비즈니스 로직을 담당하는 애플리케이션 서비스.

    로컬 캐시(Local Storage)와 클라우드 저장소(Cloud Storage) 사이의
    데이터 동기화 및 조회를 총괄한다.
    """

    def __init__(
        self,
        cloud_storage: StoragePort,
        local_storage: StoragePort,
        report_folder_id: str,
        report_dir: str = "data/report",
    ):
        """필요한 저장소 어댑터들과 함께 ReportService를 초기화합니다.

        Args:
            cloud_storage: 원격 클라우드(Google Drive 등) 리포트 저장소.
            local_storage: 로컬 캐시 및 인덱스 파일을 위한 저장소.
            report_folder_id: 클라우드 내 리포트 폴더 식별자.
            report_dir: 로컬 리포트 캐시 디렉토리 경로.
        """
        self._cloud_storage = cloud_storage
        self._local_storage = local_storage
        self._report_folder_id = report_folder_id
        self._report_dir = report_dir

        # 로컬 디렉토리 보장
        self._local_storage.ensure_directory(".")
        self._last_sync_time = 0
        self._sync_interval = 300  # 5분

    def get_reports_by_stock(self, stock_name: str) -> list[Report]:
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

    def get_report_counts(self) -> dict[str, int]:
        """종목별 리포트 수량을 집계한다."""
        counts: dict[str, int] = {}

        # 인덱스 파일 기반 집계 시도
        list_data = self._local_storage.get_file("list.json")
        if list_data:
            try:
                data = json.loads(list_data.decode("utf-8"))
                for r in data:
                    filename = r.get("filename", "")
                    if "[" in filename and "]" in filename:
                        stock = filename.split("[")[1].split("]")[0]
                        counts[stock] = counts.get(stock, 0) + 1
                return counts
            except Exception:
                pass

        # 폴백: 파일 시스템 직접 스캔
        files = self._local_storage.list_files_in_folder(".")
        for f in files:
            filename = unicodedata.normalize("NFC", f["name"])
            if filename.lower().endswith(".pdf") and "[" in filename and "]" in filename:
                try:
                    stock = filename.split("[")[1].split("]")[0]
                    counts[stock] = counts.get(stock, 0) + 1
                except Exception:
                    pass
        return counts

    def sync_index(self) -> list[str]:
        """클라우드 저장소에서 인덱스 파일들을 강제로 동기화한다."""
        updated = []
        logger.info("[ReportService] 클라우드 인덱스 동기화 시작 (folder: report)")
        try:
            # 1. list.json 동기화
            list_data = self._cloud_storage.get_file("list.json", folder="report")
            if list_data:
                self._local_storage.put_file("list.json", list_data)
                updated.append("list.json")
            else:
                logger.warning("[ReportService] 클라우드에서 list.json을 찾을 수 없습니다.")

            # 2. reports.json 동기화
            reports_data = self._cloud_storage.get_file("reports.json", folder="report")
            if reports_data:
                self._local_storage.put_file("reports.json", reports_data)
                updated.append("reports.json")
            else:
                logger.warning("[ReportService] 클라우드에서 reports.json을 찾을 수 없습니다.")

            self._last_sync_time = int(time.time())
            if updated:
                logger.info(f"[ReportService] 인덱스 동기화 완료: {', '.join(updated)}")
            else:
                logger.info("[ReportService] 동기화할 새로운 인덱스 파일이 없습니다.")
        except Exception as e:
            logger.error(f"[ReportService] 동기화 중 오류 발생: {e}", exc_info=True)

        return updated

    def get_file_content_path(self, filename: str) -> Path | None:
        """파일의 로컬 경로를 반환한다. 로컬에 없으면 클라우드로부터 다운로드한다."""
        # 1. 파일명 유효성 검사
        if not filename.lower().endswith(".pdf"):
            return None

        # 2. 로컬 존재 확인 및 다운로드
        if not self._local_storage.path_exists(filename):
            logger.info(f"[ReportService] 클라우드에서 파일 다운로드 시도 (folder: report): {filename}")
            if not self._cloud_storage.download_file(filename, str(Path(self._report_dir) / filename), folder="report"):
                logger.error(f"[ReportService] 파일 다운로드 실패 (folder: report): {filename}")
                return None

        # 3. 절대 경로 반환 (FastAPI 서빙용)
        return Path(self._report_dir) / filename

    def _load_from_list_json(self, stock_nfc: str) -> list[Report]:
        list_data = self._local_storage.get_file("list.json")
        if not list_data:
            return []

        try:
            data = json.loads(list_data.decode("utf-8"))
            results = []
            for r in data:
                f_name = r["filename"]
                if "[" in f_name and "]" in f_name:
                    try:
                        f_stock = f_name.split("[")[1].split("]")[0]
                        if f_stock == stock_nfc:
                            results.append(
                                Report(
                                    filename=f_name,
                                    stock=f_stock,
                                    title=f_name,
                                    date=r["date"],
                                    provider="Unknown",
                                    url=f"/report_files/{f_name}",
                                )
                            )
                    except Exception:
                        continue
            return sorted(results, key=lambda x: x.date, reverse=True)
        except Exception as e:
            logger.error(f"Error loading list.json: {e}")
            return []

    def _load_from_reports_json(self, stock_nfc: str) -> list[Report]:
        index_data = self._local_storage.get_file("reports.json")
        if not index_data:
            return []

        try:
            data = json.loads(index_data.decode("utf-8"))
            reports_data = data.get("reports", [])
            results = []
            for r in reports_data:
                if unicodedata.normalize("NFC", r["stock"]) == stock_nfc:
                    results.append(
                        Report(
                            filename=r["filename"],
                            stock=r["stock"],
                            title=r["title"],
                            date=r["date"],
                            provider=r["provider"],
                            url=f"/report_files/{r['filename']}",
                        )
                    )
            return sorted(results, key=lambda x: x.date, reverse=True)
        except Exception as e:
            logger.error(f"Error loading reports.json: {e}")
            return []

    def _scan_local_files(self, stock_nfc: str) -> list[Report]:
        results = []
        search_patterns = [f"[{stock_nfc}]", stock_nfc]
        files = self._local_storage.list_files_in_folder(".")
        for f in files:
            filename_nfc = unicodedata.normalize("NFC", f["name"])
            if filename_nfc.lower().endswith(".pdf") and any(p in filename_nfc for p in search_patterns):
                results.append(
                    Report(
                        filename=f["name"],
                        stock=stock_nfc,
                        title=f["name"],
                        date="Unknown",
                        provider="Manual",
                        url=f"/report_files/{f['name']}",
                    )
                )
        return sorted(results, key=lambda x: x.filename, reverse=True)
