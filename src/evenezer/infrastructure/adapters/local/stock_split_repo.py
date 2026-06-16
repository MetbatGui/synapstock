import os
import json
from pathlib import Path
import pandas as pd
from pydantic import BaseModel, Field, AliasChoices, field_validator

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
    """주식 분할(액면분할) 데이터를 로컬 파일 및 엑셀에서 관리하는 저장소 구현체."""

    def __init__(self, data_root: str = "data/statistics/stock_split"):
        self.root = Path(data_root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.root / "stock_splits_manifest.json"

    def load_manifest(self) -> StockSplitManifest | None:
        """로컬 매니페스트 정보를 불러옵니다."""
        if not self.manifest_path.exists():
            return None
        try:
            with open(self.manifest_path, encoding="utf-8") as f:
                data = json.load(f)
                return StockSplitManifest.model_validate(data)
        except Exception:
            return None

    def save_manifest(self, manifest: StockSplitManifest) -> None:
        """로컬 매니페스트 정보를 저장합니다."""
        self.root.mkdir(parents=True, exist_ok=True)
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest.model_dump(), f, indent=2, ensure_ascii=False)

    def save_excel_file(self, filename: str, content: bytes) -> None:
        """엑셀 파일 데이터를 로컬 저장소에 저장합니다."""
        self.root.mkdir(parents=True, exist_ok=True)
        file_path = self.root / filename
        with open(file_path, "wb") as f:
            f.write(content)

    def save_manifest_file(self, content: bytes) -> None:
        """매니페스트 JSON 데이터를 로컬 저장소에 저장합니다."""
        self.root.mkdir(parents=True, exist_ok=True)
        with open(self.manifest_path, "wb") as f:
            f.write(content)

    def get_file_mtime(self, filename: str) -> float | None:
        """로컬에 다운로드된 파일의 최종 수정 시간(mtime)을 구합니다."""
        file_path = self.root / filename
        if not file_path.exists():
            return None
        return file_path.stat().st_mtime

    def load_by_year(self, year: str) -> list[StockSplit]:
        """특정 연도의 주식 분할 이력을 불러옵니다."""
        # 파일은 "액면분할(YYYY년).xlsx" 형태로 저장됨
        filename = f"액면분할({year}년).xlsx"
        file_path = self.root / filename
        if not file_path.exists():
            return []

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
            return splits
        except Exception:
            return []

    def load_all(self) -> list[StockSplit]:
        """모든 주식 분할 이력을 불러옵니다."""
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

        all_splits = []
        for year in years:
            all_splits.extend(self.load_by_year(year))
            
        # 정렬: 배정기준일(base_date) 최신순으로 정렬
        all_splits.sort(key=lambda x: x.base_date or "", reverse=True)
        return all_splits
