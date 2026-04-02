"""종목 정보, 재무, 공시, 검색, 뉴스 API 라우터.

Naver Finance 자동완성, DART 공시, 재무 데이터, 뉴스 스크래핑 등
종목과 관련된 조회 및 관리 엔드포인트를 제공합니다.
"""
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from synapstock.presentation.web.core.dependencies import service

router = APIRouter()


@router.get("/api/stock/info/{ticker}")
async def get_stock_info(ticker: str) -> dict:
    """티커 심볼로 종목 기본 정보(이름, 리포트, 뉴스)를 반환합니다.

    모든 보드를 순회하여 일치하는 종목을 탐색합니다.

    Args:
        ticker (str): 조회할 종목 티커 심볼 (예: ``"005930"``).

    Returns:
        dict: 다음 키를 포함하는 딕셔너리:
            - ``ticker`` (str): 요청한 티커.
            - ``name`` (str | None): 종목명. 찾지 못한 경우 ``None``.
            - ``reports`` (list[str]): 등록된 리포트 경로 목록.
            - ``news`` (list[dict]): 등록된 뉴스 목록.

    Raises:
        JSONResponse (500): 조회 중 예외 발생 시.
    """
    try:
        boards = service.list_boards()
        for b_name in boards:
            board = service.load_board(b_name)

            def find_stock_recursive(node):
                if hasattr(node, "stocks") and node.stocks:
                    for s in node.stocks:
                        if s.ticker == ticker:
                            return s
                if hasattr(node, "nodes") and node.nodes:
                    for n in node.nodes:
                        res = find_stock_recursive(n)
                        if res:
                            return res
                return None

            root_node = getattr(board, "root", board)
            stock_obj = find_stock_recursive(root_node)

            if stock_obj:
                return {
                    "ticker": ticker,
                    "name": stock_obj.name,
                    "reports": stock_obj.reports,
                    "news": stock_obj.news,
                }

        return {"ticker": ticker, "name": None, "reports": [], "news": []}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"message": str(e)})


@router.get("/api/stock/financials")
async def get_financials(name: str) -> list:
    """특정 기업의 분기별 재무(매출) 데이터를 반환합니다.

    Args:
        name (str): 조회할 기업명.

    Returns:
        list[dict]: 분기별 재무 데이터. 항목 예시: ``{"quarter": "2024Q3", "value": 98000000}``.

    Raises:
        JSONResponse (500): 조회 중 예외 발생 시.
    """
    try:
        if not name:
            return []
        financials = service.get_financial_data(name)
        return financials
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})


@router.get("/api/stock/search")
async def search_stock(q: str) -> list:
    """Naver Stock API 자동완성 프록시 엔드포인트.

    Args:
        q (str): 검색 쿼리 문자열 (종목명 또는 티커 앞부분).

    Returns:
        list[dict]: 자동완성 결과. 각 항목은 ``{"name": str, "ticker": str}`` 형태.
    """
    results = service.search_ticker(q)
    return results


@router.get("/api/stocks/all")
async def get_all_stocks_flat() -> list:
    """모든 보드의 종목을 평탄화된 목록으로 반환합니다.

    전체 검색 기능의 클라이언트 캐싱에 사용됩니다.

    Returns:
        list[dict]: 전체 종목 목록. 각 항목은 다음 키를 포함합니다:
            - ``ticker`` (str): 티커 심볼.
            - ``name`` (str): 종목명.
            - ``board`` (str): 소속 보드 파일명.
            - ``path`` (list[str]): 루트에서 해당 종목까지의 노드 이름 경로.

    Raises:
        JSONResponse (500): 조회 중 예외 발생 시.
    """
    try:
        boards = service.list_boards()
        all_stocks = []

        for b_name in boards:
            board = service.load_board(b_name)

            def flatten_stocks(node, current_path=[]):
                stocks = []
                if hasattr(node, "stocks") and node.stocks:
                    for s in node.stocks:
                        stocks.append(
                            {
                                "ticker": s.ticker,
                                "name": s.name,
                                "board": b_name,
                                "path": current_path,
                            }
                        )
                if hasattr(node, "nodes") and node.nodes:
                    for n in node.nodes:
                        stocks.extend(flatten_stocks(n, current_path + [n.name]))
                return stocks

            root_node = getattr(board, "root", board)
            all_stocks.extend(flatten_stocks(root_node))

        return all_stocks
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})


@router.get("/api/disclosure/{ticker}")
async def get_disclosures(ticker: str) -> list:
    """특정 종목의 DART 공시 목록을 반환합니다.

    Args:
        ticker (str): 조회할 종목 티커 심볼.

    Returns:
        list[dict]: 공시 목록. 각 항목은 ``{"rcpNo": str, "title": str, "date": str}`` 형태.
            ``ticker``가 ``"none"``이거나 빈 문자열이면 빈 목록을 반환합니다.

    Raises:
        JSONResponse (500): 조회 중 예외 발생 시.
    """
    try:
        if not ticker or ticker == "none":
            return []
        disclosures = service.get_disclosures(ticker)
        return disclosures
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})


@router.get("/api/news/scrape")
async def scrape_news(url: str) -> dict:
    """뉴스 URL에서 제목과 날짜를 스크래핑하여 반환합니다.

    `og:title`, `<title>` 순으로 제목을 추출하고,
    `article:published_time` 등의 메타 태그를 우선 탐색하여 날짜를 추출합니다.
    날짜를 찾지 못하면 오늘 날짜를 사용합니다.

    Args:
        url (str): 스크래핑할 뉴스 기사 URL.

    Returns:
        dict: 다음 키를 포함하는 딕셔너리:
            - ``title`` (str): 추출된 뉴스 제목.
            - ``date`` (str): ``YYYY-MM-DD`` 형식의 날짜.
            - ``url`` (str): 요청한 원본 URL.

    Raises:
        JSONResponse (400): URL 접속에 실패한 경우 (HTTP 오류).
        JSONResponse (500): 스크래핑 중 예외 발생 시.
    """
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = response.apparent_encoding

        if response.status_code != 200:
            return JSONResponse(
                status_code=400,
                content={"message": f"URL 접속 실패: {response.status_code}"},
            )

        soup = BeautifulSoup(response.text, "html.parser")

        # 1. 제목 추출
        title = ""
        og_title = soup.find("meta", property="og:title")
        if og_title:
            title = og_title.get("content", "")
        if not title:
            title_tag = soup.find("title")
            if title_tag:
                title = title_tag.get_text().strip()

        # 2. 날짜 추출
        date_str = ""
        date_tags = [
            ("meta", {"property": "article:published_time"}),
            ("meta", {"property": "og:pubdate"}),
            ("meta", {"name": "pubdate"}),
            ("meta", {"name": "date"}),
        ]
        for tag_name, attrs in date_tags:
            tag = soup.find(tag_name, attrs)
            if tag:
                content = tag.get("content", "")
                if content:
                    date_match = re.search(r"(\d{4}[.\-/]\d{2}[.\-/]\d{2})", content)
                    if date_match:
                        date_str = date_match.group(1).replace(".", "-").replace("/", "-")
                        break

        if not date_str:
            match = re.search(r"(\d{4}[.\-/]\d{2}[.\-/]\d{2})", response.text)
            if match:
                date_str = match.group(1).replace(".", "-").replace("/", "-")
            else:
                date_str = datetime.now().strftime("%Y-%m-%d")

        return {"title": title, "date": date_str, "url": url}
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})


@router.post("/api/stock/news/add")
async def add_stock_news(board: str, ticker: str, title: str, date: str, url: str) -> dict:
    """종목에 뉴스 정보를 추가합니다.

    Args:
        board (str): 대상 보드 파일명.
        ticker (str): 뉴스를 추가할 종목 티커.
        title (str): 뉴스 기사 제목.
        date (str): ``YYYY-MM-DD`` 형식의 기사 날짜.
        url (str): 뉴스 기사 URL.

    Returns:
        dict: ``{"status": "success"}`` 또는 404 오류 응답.

    Raises:
        JSONResponse (404): 해당 종목을 찾을 수 없는 경우.
        JSONResponse (500): 처리 중 예외 발생 시.
    """
    try:
        success = service.add_stock_news(board, ticker, title, date, url)
        if success:
            return {"status": "success"}
        return JSONResponse(status_code=404, content={"message": "Stock not found"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})


@router.delete("/api/stock/news/delete")
async def delete_stock_news(board: str, ticker: str, url: str) -> dict:
    """종목에서 특정 뉴스를 삭제합니다.

    Args:
        board (str): 대상 보드 파일명.
        ticker (str): 대상 종목 티커.
        url (str): 삭제할 뉴스 기사 URL.

    Returns:
        dict: ``{"status": "success"}`` 또는 404 오류 응답.

    Raises:
        JSONResponse (404): 종목 또는 뉴스를 찾을 수 없는 경우.
        JSONResponse (500): 처리 중 예외 발생 시.
    """
    try:
        success = service.remove_stock_news(board, ticker, url)
        if success:
            return {"status": "success"}
        return JSONResponse(status_code=404, content={"message": "Stock or news not found"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})
