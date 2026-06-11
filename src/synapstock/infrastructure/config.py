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
    heatmap_dir: Path = Path("data/heatmap")
    financial_dir: Path = Path("data/financial_statements")
    statistics_dir: Path = Path("data/statistics")
    netbuy_dir: Path = Path("data/statistics/netbuy")
    ceiling_dir: Path = Path("data/statistics/ceiling")
    capital_increase_dir: Path = Path("data/statistics/capital_increase")
    bonus_issue_dir: Path = Path("data/statistics/bonus_issue")
    convertible_bond_dir: Path = Path("data/statistics/convertible_bond")
    bw_dir: Path = Path("data/statistics/bw")
    new_listing_dir: Path = Path("data/statistics/new_listing")
    weekly_change_dir: Path = Path("data/statistics/weekly_change")
    stock_split_dir: Path = Path("data/statistics/stock_split")
    news_dir: Path = Path("data/news")


    # 외부 API 토큰 (환경 변수)
    miro_token: str = ""
    telegram_token: str = ""

    # 캐시 파일 경로
    stock_cache_path: Path = Path("stock_cache.json")

    # Google Drive 폴더 ID (환경 변수)
    report_folder_id: str | None = None
    sd_folder_id: str | None = None
    ceiling_folder_id: str | None = None
    capital_increase_folder_id: str | None = None
    bonus_issue_folder_id: str | None = None
    convertible_bond_folder_id: str | None = None
    bw_folder_id: str | None = None
    new_listing_folder_id: str | None = None
    news_folder_id: str | None = None
    weekly_change_folder_id: str | None = None
    theme_folder_id: str | None = None
    financial_statements_id: str | None = None
    stock_split_folder_id: str | None = None
    heatmap_folder_id: str | None = None

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
            heatmap_dir=data_root / "heatmap",
            financial_dir=data_root / "financial_statements",
            statistics_dir=data_root / "statistics",
            netbuy_dir=data_root / "statistics" / "netbuy",
            ceiling_dir=data_root / "statistics" / "ceiling",
            capital_increase_dir=data_root / "statistics" / "capital_increase",
            bonus_issue_dir=data_root / "statistics" / "bonus_issue",
            convertible_bond_dir=data_root / "statistics" / "convertible_bond",
            bw_dir=data_root / "statistics" / "bw",
            new_listing_dir=data_root / "statistics" / "new_listing",
            weekly_change_dir=data_root / "statistics" / "weekly_change",
            stock_split_dir=data_root / "statistics" / "stock_split",
            news_dir=data_root / "news",

            miro_token=os.getenv("MIRO_ACCESS_TOKEN", ""),
            telegram_token=os.getenv("TELEGRAM_API_TOKEN", ""),
            report_folder_id=os.getenv("GOOGLE_DRIVE_REPORT_FOLDER_ID"),
            sd_folder_id=os.getenv("GOOGLE_DRIVE_SUPPLY_DEMAND_FOLDER_ID"),
            ceiling_folder_id=os.getenv("GOOGLE_DRIVE_CEILLING_FOLDER_ID"),
            capital_increase_folder_id=os.getenv("GOOGLE_DRIVE_CAPITAL_INCREASE_FOLDER_ID"),
            bonus_issue_folder_id=os.getenv("GOOGLE_DRIVE_BONUS_SHARE_FOLDER_ID"),
            convertible_bond_folder_id=os.getenv("GOOGLE_DRIVE_CONVERTIBLE_BOND_FOLDER_ID"),
            bw_folder_id=os.getenv("GOOGLE_DRIVE_BW_FOLDER_ID"),
            new_listing_folder_id=os.getenv("GOOGLE_DRIVE_NEW_LISTING_FOLDER_ID"),
            news_folder_id=os.getenv("GOOGLE_DRIVE_NEWS_FOLDER_ID"),
            weekly_change_folder_id=os.getenv("GOOGLE_DRIVE_WEEKLY_CHANGE_ID"),
            theme_folder_id=os.getenv("GOOGLE_DRIVE_THEME_FOLDER_ID"),
            financial_statements_id=os.getenv("GOOGLE_DRIVE_FINANCIAL_STATEMENTS_ID"),
            stock_split_folder_id=os.getenv("GOOGLE_DRIVE_STOCK_SPLIT_ID"),
            heatmap_folder_id=os.getenv("GOOGLE_DRIVE_HEATMAP_FOLDER_ID"),
        )
