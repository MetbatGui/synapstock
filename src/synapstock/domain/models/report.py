from dataclasses import dataclass
from datetime import date
from typing import Optional

@dataclass(frozen=True)
class Report:
    """리포트 도메인 엔티티."""
    filename: str
    stock: str
    title: str
    date: str  # YYYY-MM-DD
    provider: str
    url: Optional[str] = None

    @property
    def stock_nfc(self) -> str:
        import unicodedata
        return unicodedata.normalize("NFC", self.stock)
