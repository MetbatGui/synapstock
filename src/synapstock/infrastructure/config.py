import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict


class AppConfig(BaseModel):
    """애플리케이션 전역 설정 클래스.

    환경 변수와 하드코딩된 기본 경로를 중앙에서 관리합니다.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    # 기본 경로 설정
    data_dir: Path = Path("data")
    secrets_dir: Path = Path("secrets")

    # 서비스별 상세 경로 (data_dir 기준)
    board_dir: Path = Path("data/board")
    report_dir: Path = Path("data/report")
    pdf_dir: Path = Path("data/pdf")
    financial_dir: Path = Path("data/financial_statements")
    statistics_dir: Path = Path("data/statistics")
    netbuy_dir: Path = Path("data/statistics/netbuy")
    ceiling_dir: Path = Path("data/statistics/ceiling")
    capital_increase_dir: Path = Path("data/statistics/capital_increase")

    # 외부 API 토큰 (환경 변수)
    miro_token: str = ""
    telegram_token: str = ""

    # 캐시 파일 경로
    stock_cache_path: Path = Path("stock_cache.json")

    # Google Drive 폴더 ID (환경 변수)
    report_folder_id: str | None = None
    sd_folder_id: str | None = None
    ceiling_folder_id: str | None = None

    @classmethod
    def load(cls, load_env: bool = True) -> "AppConfig":
        """.env 파일과 시스템 환경 변수로부터 설정을 로드합니다."""
        if load_env:
            load_dotenv()

        # 기본 경로 인스턴스 생성
        data_root = Path(os.getenv("DATA_DIR", "data"))
        secrets_root = Path(os.getenv("SECRETS_DIR", "secrets"))

        return cls(
            data_dir=data_root,
            secrets_dir=secrets_root,
            board_dir=data_root / "board",
            report_dir=data_root / "report",
            pdf_dir=data_root / "pdf",
            financial_dir=data_root / "financial_statements",
            statistics_dir=data_root / "statistics",
            netbuy_dir=data_root / "statistics" / "netbuy",
            ceiling_dir=data_root / "statistics" / "ceiling",
            capital_increase_dir=data_root / "statistics" / "capital_increase",
            miro_token=os.getenv("MIRO_ACCESS_TOKEN", ""),
            telegram_token=os.getenv("TELEGRAM_API_TOKEN", ""),
            report_folder_id=os.getenv("GOOGLE_DRIVE_REPORT_FOLDER_ID"),
            sd_folder_id=os.getenv("GOOGLE_DRIVE_SUPPLY_DEMAND_FOLDER_ID"),
            ceiling_folder_id=os.getenv("GOOGLE_DRIVE_CEILLING_FOLDER_ID")
        )
