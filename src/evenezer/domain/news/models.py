from datetime import datetime

from pydantic import BaseModel, Field


class NewsItem(BaseModel):
    """시스템에 저장된 개별 뉴스 항목 모델."""

    id: str = Field(..., description="URL 해시 기반 고유 식별자")
    title: str = Field(..., description="뉴스 제목")
    url: str = Field(..., description="뉴스 원문 링크")
    collected_at: datetime = Field(default_factory=datetime.now, description="시스템 저장 시각")

    # 연관 종목 정보 (있을 경우만 저장)
    ticker: str | None = None
    stock_name: str | None = None

class NewsBatch(BaseModel):
    """특정 날짜(저장일 기준)에 수집된 뉴스 묶음."""

    date: str = Field(..., description="저장 날짜 (YYYY-MM-DD)")
    items: list[NewsItem] = Field(default_factory=list)
    last_modified: datetime = Field(default_factory=datetime.now, description="배치 데이터 최종 변경 시각")

    @property
    def count(self) -> int:
        return len(self.items)
