"""종목 정보, 재무, 공시, 검색, 뉴스 API 라우터.

Naver Finance 자동완성, DART 공시, 재무 데이터, 뉴스 스크래핑 등
종목과 관련된 조회 및 관리 엔드포인트를 제공합니다.
"""

from typing import cast

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from synapstock.presentation.web.core.dependencies import media_service, news_service, query_service

router = APIRouter()


@router.get("/api/stock/info/{ticker}", response_model=None)
async def get_stock_info(ticker: str) -> dict | JSONResponse:
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
        result = query_service.get_stock_by_ticker(ticker)

        if result:
            stock_obj, b_name, path = result

            # 중앙 뉴스 아카이브에서 해당 종목 뉴스 가져오기
            archived_news = news_service.get_news_for_stock(ticker)
            news_list = [
                {"title": n.title, "url": n.url, "date": n.collected_at.strftime("%Y-%m-%d")}
                for n in archived_news
            ]

            return {
                "ticker": ticker,
                "name": stock_obj.name,
                "reports": [r.split("/")[-1] for r in stock_obj.reports], # 파일명만 추출
                "news": news_list,
                "path": path,
            }

        return {"ticker": ticker, "name": None, "reports": [], "news": [], "path": []}
    except Exception as e:
        import traceback

        traceback.print_exc()
        return JSONResponse(status_code=500, content={"message": str(e)})


@router.get("/api/stock/financials", response_model=None)
async def get_financials(name: str, metric: str = "매출액", period: str = "분기별") -> list | JSONResponse:
    """특정 기업의 재무 데이터를 반환합니다 (지표 및 기간 선택 가능).

    Args:
        name (str): 조회할 기업명.
        metric (str): 조회할 지표 (매출액, 영업이익, 당기순이익). 기본값 "매출액".
        period (str): 조회 기간 (분기별, 연간). 기본값 "분기별".

    Returns:
        list[dict]: 재무 데이터 목록.
    """
    try:
        if not name:
            return []
        financials = query_service.get_financial_data(name, metric, period)
        return cast(list, financials)
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})


@router.get("/api/stock/search", response_model=None)
async def search_stock(q: str = "") -> list | JSONResponse:
    """종목명 또는 티커로 검색하여 결과를 반환합니다."""
    try:
        results = query_service.search_ticker(q)
        return cast(list, results)
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})


@router.get("/api/stocks/all", response_model=None)
async def get_all_stocks_flat() -> list | JSONResponse:
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
        results = query_service.get_all_stocks_flat()
        return cast(list, results)
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})


@router.get("/api/disclosure/{ticker}", response_model=None)
async def get_disclosures(ticker: str) -> list | JSONResponse:
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
        disclosures = query_service.get_disclosures(ticker)
        return cast(list, disclosures)
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})


@router.get("/api/news/scrape", response_model=None)
async def scrape_news(url: str) -> dict | JSONResponse:
    """뉴스 URL에서 제목과 날짜를 스크래핑하여 반환합니다.
    NewsService를 사용하여 일관된 스크래핑 결과를 보장합니다.
    """
    if not (url.startswith("http://") or url.startswith("https://")):
        return JSONResponse(status_code=400, content={"message": "Invalid URL format"})

    try:
        # NewsService의 스크래퍼 어댑터 활용
        scraped = await news_service.scraper.scrape(url)
        if not scraped or not scraped.title:
            return JSONResponse(status_code=400, content={"message": "뉴스 정보를 추출할 수 없습니다."})

        return {"title": scraped.title, "date": scraped.date, "url": url}
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})


@router.post("/api/stock/news/add", response_model=None)
async def add_stock_news(board: str, ticker: str, title: str, date: str, url: str) -> dict | JSONResponse:
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
        success = await media_service.add_stock_news(board, ticker, title, date, url)
        if success:
            return {"status": "success"}
        return JSONResponse(status_code=404, content={"message": "Stock not found"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})


@router.delete("/api/stock/news/delete", response_model=None)
async def delete_stock_news(board: str, ticker: str, url: str) -> dict | JSONResponse:
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
        success = await media_service.remove_stock_news(board, ticker, url)
        if success:
            return {"status": "success"}
        return JSONResponse(status_code=404, content={"message": "Stock or news not found"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})
