"""Board 도메인 모델 정의."""

from __future__ import annotations

from pydantic import BaseModel


class Stock(BaseModel):
    """주식 종목 모델.

    Attributes:
        name: 종목명.
        ticker: 종목 코드 (예: '005930').
    """

    name: str
    ticker: str
