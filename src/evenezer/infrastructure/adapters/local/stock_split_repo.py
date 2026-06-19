import json
from pathlib import Path

import pandas as pd
from pydantic import AliasChoices, BaseModel, Field, field_validator

from evenezer.domain.ports import StockSplitRepositoryPort
from evenezer.domain.statistics.models import StockSplit, StockSplitManifest


class StockSplitExcelDTO(BaseModel):
    """엑셀 파일에서 읽어온 주식 분할 날 데이터 가공 및 정제를 위한 DTO."""

    company_name: str = Field(validation_alias=AliasChoices("회사명", "company_name"))
    market: str | None = Field(default=None, validation_alias=AliasChoices("시장", "market"))
    disclosure_type: str | None = Field(default=None, validation_alias=AliasChoices("공시구분", "철회여부", "disclosure_type"))
    base_date: str = Field(validation_alias=AliasChoices("배정기준일", "등록일자", "base_date"))
    board_resolution_date: str | None = Field(default=None, validation_alias=AliasChoices("이사회결의일", "board_resolution_date"))
    receipt_no: str = Field(validation_alias=AliasChoices("접수번호", "공시번호", "receipt_no"))
    original_receipt_no: str | None = Field(default=None, validation_alias=AliasChoices("원접수번호", "이전공시번호", "original_receipt_no"))
    prev_shares: int | None = Field(default=None, validation_alias=AliasChoices("발행주식수(이전)", "분할전 보통주식수(주)", "prev_shares"))
    post_shares: int | None = Field(default=None, validation_alias=AliasChoices("발행주식수(이후)", "분할후 보통주식수(주)", "post_shares"))
    split_ratio: float | None = Field(default=None, validation_alias=AliasChoices("분할비율", "분할배율", "split_ratio"))
    listing_date: str | None = Field(default=None, validation_alias=AliasChoices("신주상장예정일", "listing_date"))
    general_meeting_date: str | None = Field(default=None, validation_alias=AliasChoices("주총결의일", "general_meeting_date"))
    first_disclosure_date: str | None = Field(default=None, validation_alias=AliasChoices("최초공시 등록일자", "first_disclosure_date"))

    @field_validator("market", "disclosure_type", mode="before")
    @classmethod
    def normalize_strings(cls, v):
        if not v or (isinstance(v, float) and (v != v or v is None)):
            return None
        s = str(v).strip()
        if s.lower() in ("nan", ""):
            return None
        return s

    @field_validator("base_date", "board_resolution_date", "listing_date", "general_meeting_date", "first_disclosure_date", mode="before")
    @classmethod
    def normalize_date(cls, v):
        if not v or (isinstance(v, float) and (v != v or v is None)): # NaN check
            return None
        s = str(v).strip()
        if s.lower() in ("nan", ""):
            return None
        s = s.replace(".", "-")
        if " " in s:
            s = s.split(" ")[0]
        return s

    @field_validator("split_ratio", mode="before")
    @classmethod
    def normalize_split_ratio(cls, v):
        if not v or (isinstance(v, float) and (v != v or v is None)):
            return None
        s = str(v).strip().lower()
        if s in ("nan", ""):
            return None
        try:
            return float(s)
        except ValueError:
            return None

    @field_validator("prev_shares", "post_shares", mode="before")
    @classmethod
    def normalize_shares(cls, v):
        if not v or (isinstance(v, float) and (v != v or v is None)):
            return None
        s = str(v).strip().lower()
        if s in ("nan", ""):
            return None
        try:
            return int(float(s))
        except ValueError:
            return None

    @field_validator("receipt_no", "original_receipt_no", mode="before")
    @classmethod
    def normalize_receipt_no(cls, v):
        if not v or (isinstance(v, float) and (v != v or v is None)):
            return None
        s = str(v).strip().lower()
        if s in ("nan", ""):
            return None
        try:
            if "." in s:
                return str(int(float(s)))
            return s
        except ValueError:
            return s

    def to_domain(self) -> StockSplit:
        """가공 및 검증이 완료된 DTO 객체를 순수 도메인 모델로 변환합니다."""
        return StockSplit(
            company_name=self.company_name,
            market=self.market,
            disclosure_type=self.disclosure_type,
            base_date=self.base_date,
            board_resolution_date=self.board_resolution_date,
            receipt_no=self.receipt_no,
            original_receipt_no=self.original_receipt_no,
            prev_shares=self.prev_shares,
            post_shares=self.post_shares,
            split_ratio=self.split_ratio,
            listing_date=self.listing_date,
            general_meeting_date=self.general_meeting_date,
            first_disclosure_date=self.first_disclosure_date,
        )


class LocalStockSplitRepository(StockSplitRepositoryPort):
    """주식 분할(액면분할/병합) 데이터를 로컬 파일 및 Excel 파일로부터 로드하여 관리하는 저장소 어댑터입니다."""

    def __init__(self, data_root: str = "data/statistics/stock_split"):
        """LocalStockSplitRepository를 초기화합니다.

        Args:
            data_root: 주식 분할 관련 데이터 파일이 저장되는 디렉터리 경로.
        """
        self.root = Path(data_root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.root / "stock_splits_manifest.json"
        self._cache = {}  # year -> list[StockSplit]
        self._all_cache = None  # list[StockSplit] | None
        self._last_mtimes = {}  # filename -> float

    def load_manifest(self) -> StockSplitManifest | None:
        """로컬 저장소로부터 주식 분할 데이터 연도별 매니페스트 정보를 로드합니다.

        Returns:
            StockSplitManifest 객체, 파일이 없거나 예외 발생 시 None.
        """
        if not self.manifest_path.exists():
            return None
        try:
            with open(self.manifest_path, encoding="utf-8") as f:
                data = json.load(f)
                return StockSplitManifest.model_validate(data)
        except Exception:
            return None

    def save_manifest(self, manifest: StockSplitManifest) -> None:
        """현재 주식 분할 매니페스트 정보를 JSON 파일에 직렬화하여 영속화합니다.

        Args:
            manifest: 저장할 StockSplitManifest 인스턴스.
        """
        self.root.mkdir(parents=True, exist_ok=True)
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest.model_dump(), f, indent=2, ensure_ascii=False)

    def save_excel_file(self, filename: str, content: bytes) -> None:
        """구글 드라이브 등으로부터 수집된 Excel 원본 데이터 바이트를 로컬 파일로 저장합니다.

        Args:
            filename: 저장할 Excel 파일명.
            content: 파일에 기록할 바이너리 바이트.
        """
        self.root.mkdir(parents=True, exist_ok=True)
        file_path = self.root / filename
        with open(file_path, "wb") as f:
            f.write(content)
        # 엑셀 파일이 명시적으로 저장되면 해당 엑셀 캐시와 전체 캐시를 무효화
        self._all_cache = None
        year_part = filename.split("액면분할(")[1].split("년)")[0] if "액면분할(" in filename else None
        if year_part and year_part in self._cache:
            del self._cache[year_part]

    def save_manifest_file(self, content: bytes) -> None:
        """매니페스트 JSON 원본 바이트 데이터를 로컬에 즉시 파일로 영속화합니다.

        Args:
            content: 매니페스트 파일 내용 바이트.
        """
        self.root.mkdir(parents=True, exist_ok=True)
        with open(self.manifest_path, "wb") as f:
            f.write(content)
        # 매니페스트 변경 시 전체 캐시 무효화
        self._all_cache = None

    def get_file_mtime(self, filename: str) -> float | None:
        """로컬 저장소 내의 주식 분할 데이터 파일의 마지막 수정 시각(timestamp)을 조회합니다.

        Args:
            filename: 대상 파일명.

        Returns:
            마지막 수정 시각을 나타내는 float timestamp, 파일이 없을 경우 None.
        """
        file_path = self.root / filename
        if not file_path.exists():
            return None
        return file_path.stat().st_mtime

    def load_by_year(self, year: str) -> list[StockSplit]:
        """특정 연도의 주식 분할 이력 데이터를 Excel 파일로부터 파싱하여 도메인 객체 목록으로 반환합니다.

        엑셀 데이터 중 비어 있는 행은 필터링하며, Pydantic DTO를 거쳐 형식 검증 및 클렌징을 적용합니다.

        Args:
            year: 조회 및 파싱 대상 연도 구분 문자열.

        Returns:
            정제 완료된 StockSplit 도메인 모델 목록.
        """
        # 파일은 "액면분할(YYYY년).xlsx" 형태로 저장됨
        filename = f"액면분할({year}년).xlsx"
        file_path = self.root / filename
        if not file_path.exists():
            return []

        current_mtime = self.get_file_mtime(filename) or 0.0
        cached_mtime = self._last_mtimes.get(filename, 0.0)

        if year in self._cache and current_mtime == cached_mtime:
            return self._cache[year]

        try:
            # 엑셀을 Pandas DataFrame으로 로드
            # 시트명은 "주식분할_YYYY년"
            sheet_name = f"주식분할_{year}년"

            # 파일 및 시트 로드 시도
            xl = pd.ExcelFile(file_path)
            if sheet_name not in xl.sheet_names:
                # 시트명이 다를 경우 첫 번째 시트 사용
                sheet_name = xl.sheet_names[0]

            df = xl.parse(sheet_name)

            records = df.to_dict(orient="records")
            splits = []
            for record in records:
                try:
                    # 빈 행(회사명이 없거나 비어있는 경우) 스킵
                    company = record.get("회사명") or record.get("company_name")
                    if not company or (isinstance(company, float) and pd.isna(company)):
                        continue
                    # DTO를 통해 데이터를 클렌징하고 검증한 후 도메인 엔티티로 변환
                    dto = StockSplitExcelDTO.model_validate(record)
                    splits.append(dto.to_domain())
                except Exception:
                    # 파싱 에러 엣지 케이스는 조용히 로그만 남기거나 스킵하여 전체 데이터를 보존함
                    continue

            self._cache[year] = splits
            self._last_mtimes[filename] = current_mtime
            self._all_cache = None
            return splits
        except Exception:
            return []

    def load_all(self) -> list[StockSplit]:
        """현재 로컬 저장소에 누적된 모든 연도의 주식 분할 이력 데이터를 병합하여 반환합니다.

        반환 결과는 배정기준일(base_date) 최신순으로 정렬됩니다.

        Returns:
            전체 StockSplit 도메인 모델 목록.
        """
        manifest = self.load_manifest()
        years = []
        if manifest:
            years = manifest.supported_years
        else:
            # 매니페스트가 없는 경우 디렉토리 내의 파일 이름 매칭 시도
            for file_path in self.root.glob("액면분할(*년).xlsx"):
                # '액면분할(' (5자) 이후 '년' 전까지 추출
                try:
                    year_part = file_path.name.split("액면분할(")[1].split("년)")[0]
                    years.append(year_part)
                except Exception:
                    continue
            years = sorted(list(set(years)))

        any_changed = False
        for year in years:
            filename = f"액면분할({year}년).xlsx"
            current_mtime = self.get_file_mtime(filename) or 0.0
            cached_mtime = self._last_mtimes.get(filename, 0.0)
            if current_mtime != cached_mtime:
                any_changed = True
                break

        if self._all_cache is not None and not any_changed:
            return self._all_cache

        all_splits = []
        for year in years:
            all_splits.extend(self.load_by_year(year))

        # 정렬: 배정기준일(base_date) 최신순으로 정렬
        all_splits.sort(key=lambda x: x.base_date or "", reverse=True)
        self._all_cache = all_splits
        return all_splits
