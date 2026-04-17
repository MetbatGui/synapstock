# v1.0.1 - StatisticsService fix for TypeError
import io
import logging
import re
from datetime import datetime
from typing import Any, cast

import pandas as pd

from synapstock.domain.statistics.models import (
    AnalyzedRankingItem,
    CeilingAnalysisReport,
    DailyMarketRanking,
    DailyMarketRankingAnalysis,
    MarketType,
    MonthlyMarketStats,
    RankingItem,
    SupplySubject,
)
from synapstock.infrastructure.parsers.excel_statistics_parser import (
    ExcelStatisticsParser,
)

logger = logging.getLogger(__name__)


class StatisticsService:
    """통계 데이터를 관리하고 동기화하는 애플리케이션 서비스.

    Google Drive 등 원격 스토리지를 통해 통계 엑셀 데이터를 가져오고,
    이를 로컬 저장소에 캐싱하며, 가공된 데이터를 분석하여 프론트엔드에 제공합니다.
    """

    def __init__(
        self,
        storage: Any = None,
        repository: Any = None,
        query_service: Any = None,
        ceiling_repository: Any = None,
        market_data_service: Any = None,
    ):
        """StatisticsService 객체를 초기화합니다.

        Args:
            storage: 원격 저장소 (Google Drive 등).
            repository: 일별 수급 순위 로컬/DB 저장소.
            query_service: 종목(티커) 쿼리용 서비스 (옵션).
            ceiling_repository: 상한가 관리용 로컬 저장소.
            market_data_service: 시장 데이터 수집기 서비스.
        """
        self._storage = storage
        self._repository = repository
        self._query_service = query_service
        self._ceiling_repo = ceiling_repository
        self._market_data_service = market_data_service
        self._parser = ExcelStatisticsParser()

    def _build_local_ticker_map(self) -> dict[str, str]:
        """마인드맵 보드의 모든 종목명-티커 매핑을 가져옵니다.

        Returns:
            Dict[str, str]: {종목명: 티커} 형태의 매핑 딕셔너리.
        """
        ticker_map: dict[str, str] = {}
        if not self._query_service:
            return ticker_map

        try:
            # 모든 보드의 종목 정보를 평탄화하여 가져옴
            all_stocks = cast(list[dict], self._query_service.get_all_stocks_flat())
            for stock in all_stocks:
                name = stock.get('name')
                ticker = stock.get('ticker')
                aliases = stock.get('aliases', [])
                if name and ticker:
                    ticker_map[name] = ticker
                    # 별칭들도 모두 동일한 티커로 매핑
                    for alias in aliases:
                        if alias:
                            ticker_map[alias] = ticker
        except Exception as e:
            logger.error(f"[StatisticsService] 로컬 티커 맵 빌드 실패: {e}")

        return ticker_map

    def save_rankings(self, rankings: list[DailyMarketRanking]):
        """파싱된 랭킹 리스트를 애플리케이션 저장소에 영구 저장합니다.

        Args:
            rankings (List[DailyMarketRanking]): 저장할 일별 수급 순위 데이터 리스트.
        """
        if not self._repository:
            return
        for ranking in rankings:
            self._repository.save_daily_ranking(ranking)


    def get_daily_ranking(
        self,
        date: str,
        market: MarketType,
        subject: SupplySubject,
        force_sync: bool = False
    ) -> DailyMarketRanking | None:
        """특정 날짜의 수급 순위 데이터를 가져옵니다."""
        if self._repository and not force_sync:
            cached = self._repository.load_ranking(date, market, subject)
            if cached:
                return cast(DailyMarketRanking, cached)

        # 저장소에 없으면 클라우드 동기화 시도
        all_rankings = self._fetch_and_sync_rankings(date)
        for r in all_rankings:
            if r.market == market and r.subject == subject:
                return r

        return None

    def sync_from_storage(self, date_str: str) -> list[DailyMarketRanking]:
        """지정된 날짜의 통계 데이터를 클라우드 스토리지에서 수동으로 강제 동기화합니다."""
        logger.info(f"[StatisticsService] 특정 날짜 동기화 시도: {date_str}")
        return cast(list[DailyMarketRanking], self._fetch_and_sync_rankings(date_str))

    def _fetch_and_sync_rankings(self, date_str: str) -> list[DailyMarketRanking]:
        """클라우드 스토리지에서 엑셀 파일을 다운로드하여 파싱하고 로컬 저장소에 캐싱합니다.

        Args:
            date_str (str): 기준 날짜 (YYYY-MM-DD 형식).

        Returns:
            List[DailyMarketRanking]: 파싱된 모든 마켓/주체별 랭킹 리스트. 실패 시 빈 리스트.
        """
        if not self._storage:
            return []

        year = date_str[:4]
        date_clean = date_str.replace("-", "")
        filename = f"{year}년/일별수급정리표/{year}일별수급순위정리표.xlsx"
        sheet_name = date_clean[-4:]

        content = self._storage.get_file(filename, folder="sd")
        if not content:
            return []

        try:
            rankings = self._parser.parse_summary_table(content, sheet_name, date_str)
            
            # 종목명 정규화 (별칭 -> 정규 사명)
            for ranking in rankings:
                for item in ranking.items:
                    self._normalize_item_name(item)

            self.save_rankings(rankings)
            logger.info(f"[StatisticsService] 구글 드라이브 동기화 및 캐싱 완료: {date_str}")
            return cast(list[DailyMarketRanking], rankings)
        except Exception as e:
            logger.error(f"[StatisticsService] 파싱 실패 ({filename}, 시트:{sheet_name}): {e}")
            return []

    def _normalize_item_name(self, item: RankingItem) -> None:
        """TickerSearchPort를 활용하여 종목명을 정규 사명으로 치환합니다."""
        if not self._query_service:
            return
            
        try:
            # query_service.search_ticker는 내부적으로 정규화된 NaverTickerSearchAdapter를 사용함
            search_results = self._query_service.search_ticker(item.name)
            if search_results:
                # 첫 번째 검색 결과(캐시 우선 일치 항목)의 사명으로 업데이트
                best_match = search_results[0]
                if item.name != best_match["name"]:
                    logger.debug(f"[StatisticsService] 종목명 정규화: {item.name} -> {best_match['name']}")
                    item.name = best_match["name"]
                
                # 티커 정보가 누락된 경우에도 보완
                if not item.ticker:
                    item.ticker = best_match["ticker"]
        except Exception as e:
            logger.warning(f"[StatisticsService] 종목명 정규화 실패 ({item.name}): {e}")

    def sync_recent_data(self, limit: int = 5) -> int:
        """클라우드 스토리지를 탐색하여 최신 통계 데이터를 일괄 동기화합니다.

        당해년도 통합 엑셀 문서(`YYYY일별수급순위정리표.xlsx`) 하나를 읽어들인 뒤,
        내부에 있는 최신 시트(`limit`개)들을 로컬로 일괄 파싱하여 저장합니다.

        Args:
            limit (int, optional): 동기화할 최대 최신 시트(일자) 수. 기본값 5.

        Returns:
            int: 성공적으로 동기화 처리된 일자(시트) 수.
        """
        if not self._storage:
            return 0

        logger.info("[StatisticsService] 최근 수급 통계 데이터 탐색 시작 (Google Drive)")

        try:
            year = str(datetime.now().year)
            filename = f"{year}년/일별수급정리표/{year}일별수급순위정리표.xlsx"

            content = self._storage.get_file(filename, folder="sd")
            if not content:
                logger.warning(f"[StatisticsService] 클라우드 통합 파일을 찾을 수 없음: {filename}")
                return 0

            xl = pd.ExcelFile(io.BytesIO(content))
            sheet_names = xl.sheet_names

            # 4자리 숫자(MMDD)로 된 시트명만 필터링
            date_sheets = [s for s in sheet_names if len(s) == 4 and s.isdigit()]
            # 최신순 (문자열 내림차순) 정렬
            date_sheets.sort(reverse=True)

            target_sheets = date_sheets[:limit]

            synced_count = 0
            for sheet_name in target_sheets:
                # MM-DD 포맷을 YYYY-MM-DD로 변환
                formatted_date = f"{year}-{sheet_name[:2]}-{sheet_name[2:]}"
                if self._fetch_and_sync_rankings(formatted_date):
                    synced_count += 1

            logger.info(f"[StatisticsService] 총 {synced_count}개 일자 동기화 완료")
            
            # [추가] 구글 동기화 완료 후 KRX 데이터 연쇄 수집
            if self._market_data_service:
                logger.info("[StatisticsService] 연쇄 작업 시작: KRX 데이터 동기화 트리거")
                # 최신 시트의 날짜가 있으면 해당 날짜로, 없으면 당일로 수집
                latest_date = target_sheets[0].replace("-", "") if target_sheets else None
                self._market_data_service.sync_daily_data(latest_date)

            return synced_count
        except Exception as e:
            logger.error(f"[StatisticsService] 일괄 동기화 실패: {e}", exc_info=True)
            return 0

    def get_monthly_ranking(
        self,
        year_month: str,
        market: MarketType,
        subject: SupplySubject
    ) -> MonthlyMarketStats:
        """지정된 월의 일별 데이터를 모두 취합하여 누적 수급 TOP 30 랭킹을 산출합니다."""
        if not self._repository:
            return MonthlyMarketStats(month=year_month, market=market, subject=subject, items=[])

        available_dates = cast(list[str], self._repository.list_available_dates(market, subject))
        target_dates = [d for d in available_dates if d.startswith(year_month)]

        if not target_dates:
            logger.info(
                f"[StatisticsService] {year_month} ({market}, {subject})에 해당하는 데이터가 없습니다."
            )
            return MonthlyMarketStats(month=year_month, market=market, subject=subject, items=[])

        logger.info(f"[StatisticsService] {year_month} 월간 집계 시작 (대상 일수: {len(target_dates)}일)")

        # 1. 데이터 누적
        accumulation = self._aggregate_monthly_amounts(target_dates, market, subject)

        # 2. 정렬 및 상위 항목 추출
        sorted_items = sorted(accumulation.items(), key=lambda x: x[1], reverse=True)[:30]

        # 3. 데이터 보강 (티커 매핑 등)
        local_ticker_map = self._build_local_ticker_map()
        ranking_items = [
            RankingItem(
                rank=rank, name=name, amount=int(amount),
                ticker=local_ticker_map.get(name), high_price_type=None
            )
            for rank, (name, amount) in enumerate(sorted_items, 1)
        ]

        logger.info(f"[StatisticsService] 월간 집계 완료: {year_month} ({len(ranking_items)}개 항목)")
        return MonthlyMarketStats(month=year_month, market=market, subject=subject, items=ranking_items)

    def _aggregate_monthly_amounts(
        self,
        target_dates: list[str],
        market: MarketType,
        subject: SupplySubject
    ) -> dict[str, float]:
        """지정된 기간(일자 리스트) 동안의 종목별 순매수 합계를 계산합니다.

        Args:
            target_dates (List[str]): 합산 대상 거래일 리스트.
            market (MarketType): 시장 유형.
            subject (SupplySubject): 수급 주체.

        Returns:
            Dict[str, float]: {종목명: 누적합계} 형태의 딕셔너리.
        """
        accumulation: dict[str, float] = {}
        for date_str in target_dates:
            daily = self._repository.load_ranking(date_str, market, subject)
            if not daily:
                continue
            for item in daily.items:
                accumulation[item.name] = accumulation.get(item.name, 0.0) + float(item.amount)
        return accumulation

    def get_analyzed_ranking(
        self,
        date: str,
        market: MarketType,
        subject: SupplySubject,
        force_sync: bool = False
    ) -> DailyMarketRankingAnalysis | None:
        """순위 변동 및 연속 등장 횟수가 포함된 분석 랭킹 데이터를 제공합니다."""
        raw = self.get_daily_ranking(date, market, subject, force_sync=force_sync)
        if not raw or not self._repository:
            return None

        available_dates = cast(list[str], self._repository.list_available_dates(market, subject))
        try:
            current_idx = available_dates.index(date)
        except ValueError:
            analyzed_items = [AnalyzedRankingItem(**item.model_dump(), is_new=True) for item in raw.items]
            return DailyMarketRankingAnalysis(date=date, market=market, subject=subject, items=analyzed_items)

        # 1. 이전 거래일 데이터 확보
        prev_map = {}
        prev_date = available_dates[current_idx + 1] if current_idx + 1 < len(available_dates) else None
        if prev_date:
            prev_ranking = self._repository.load_ranking(prev_date, market, subject)
            if prev_ranking:
                prev_map = {item.name: item.rank for item in prev_ranking.items}

        # 2. 지표 계산 및 데이터 보강
        local_ticker_map = self._build_local_ticker_map()
        analyzed_items = []
        for item in raw.items:
            analyzed = self._calculate_rank_metrics(item, prev_map, current_idx, available_dates, market, subject)
            analyzed.ticker = local_ticker_map.get(item.name)
            analyzed_items.append(analyzed)

        return DailyMarketRankingAnalysis(
            date=date, market=market, subject=subject, items=analyzed_items, previous_date=prev_date
        )

    def _calculate_rank_metrics(
        self,
        item: RankingItem,
        prev_map: dict[str, int],
        current_idx: int,
        available_dates: list[str],
        market: MarketType,
        subject: SupplySubject
    ) -> AnalyzedRankingItem:
        """단일 종목에 대해 이전 기록(순위 변동, 연속 등장) 지표를 분석합니다.

        Args:
            item (RankingItem): 현재 시점의 종목 데이터.
            prev_map (Dict[str, int]): {종목명: 이전순위} 맵.
            current_idx (int): 전체 날짜 목록 중 현재 날짜의 인덱스.
            available_dates (List[str]): 가용한 전체 거래일 목록.
            market (MarketType): 시장 유형.
            subject (SupplySubject): 수급 주체.

        Returns:
            AnalyzedRankingItem: 분석 결과(이전순위, 변동폭, 연속일)가 포함된 확장 모델.
        """
        analyzed = AnalyzedRankingItem(**item.model_dump())

        # 1. 이전 순위 정보 설정 (나머지 지표는 모델이 자동 계산)
        if item.name in prev_map:
            analyzed.prev_rank = prev_map[item.name]

        # 연속 등장 횟수 계산
        consecutive = 1
        lookback_limit = 10
        for i in range(current_idx + 1, min(current_idx + 1 + lookback_limit, len(available_dates))):
            past_ranking = self._repository.load_ranking(available_dates[i], market, subject)
            if past_ranking and any(p.name == item.name for p in past_ranking.items):
                consecutive += 1
            else:
                break
        analyzed.consecutive_days = consecutive
        return analyzed

    def get_daily_summary(self, date: str, force_sync: bool = False) -> dict[str, Any]:
        """지정된 날짜의 모든 시장/주체 조합 통계를 가져옵니다.

        Args:
            date (str): 조회 날짜 (YYYY-MM-DD).
            force_sync (bool, optional): 강제 동기화 여부. Defaults to False.

        Returns:
            Dict[str, Any]: {시장: {주체: 분석데이터}} 형태의 요약 객체.
        """
        logger.debug(f"[StatisticsService] get_daily_summary 호출: date={date}, force_sync={force_sync}")
        return {
            "date": date,
            "KOSPI": {
                "FOREIGN": self.get_analyzed_ranking(
                    date, MarketType.KOSPI, SupplySubject.FOREIGN, force_sync=force_sync
                ),
                "INSTITUTION": self.get_analyzed_ranking(
                    date, MarketType.KOSPI, SupplySubject.INSTITUTION, force_sync=force_sync
                )
            },
            "KOSDAQ": {
                "FOREIGN": self.get_analyzed_ranking(
                    date, MarketType.KOSDAQ, SupplySubject.FOREIGN, force_sync=force_sync
                ),
                "INSTITUTION": self.get_analyzed_ranking(
                    date, MarketType.KOSDAQ, SupplySubject.INSTITUTION, force_sync=force_sync
                )
            }
        }

    def get_ceiling_analysis(
        self,
        date: str,
        force_sync: bool = False
    ) -> CeilingAnalysisReport | None:
        """특정 날짜의 상한가 분석 리포트를 가져옵니다 (캐시 우선)."""
        if not self._ceiling_repo:
            return None

        # 1. 로컬 캐시 확인
        if not force_sync:
            cached = self._ceiling_repo.load_report(date)
            if cached:
                return cast(CeilingAnalysisReport, cached)

        # 2. 원격 데이터 가져오기 및 파싱
        report = self._fetch_remote_ceiling_report(date)
        if not report:
            return None

        # 3. 데이터 보강 (티커, 신고가 태그 등)
        self._enrich_ceiling_report_data(report, date, force_sync)

        # 4. 저장 및 반환
        self._ceiling_repo.save_report(report)
        return report

    def _fetch_remote_ceiling_report(self, date: str) -> CeilingAnalysisReport | None:
        """클라우드 스토리지에서 해당 일자의 상한가 분석 시트를 파싱합니다.

        Args:
            date (str): 조회 날짜 (YYYY-MM-DD 형식).

        Returns:
            Optional[CeilingAnalysisReport]: 파싱된 일자별 상한가 분석 리포트. 실패 시 None.
        """
        if not self._storage:
            return None

        year = date[:4]
        filename = f"상한가분석({year}년).xlsx"
        sheet_name = date[2:4] + date[5:7] + date[8:10] # YYMMDD

        content = self._storage.get_file(filename, folder="ceiling")
        if not content:
            return None

        try:
            report = self._parser.parse_ceiling_report(
                content=content, title=f"{year}년 상한가 분석 ({date})", sheet_name=sheet_name
            )
            if report:
                report.end_date = date
            return cast(CeilingAnalysisReport, report)
        except Exception as e:
            logger.error(f"[StatisticsService] 상한가 파싱 실패: {e}")
            return None

    def _enrich_ceiling_report_data(self, report: CeilingAnalysisReport, date: str, force_sync: bool):
        """리포트의 각 종목에 대해 티커 매핑 및 당일 신고가 배지 정보를 보강합니다.

        Args:
            report (CeilingAnalysisReport): 보강할 대상 리포트.
            date (str): 기준 날짜.
            force_sync (bool): 신고가 정보를 가져올 때 강제 동기화 여부.
        """
        ticker_map = self._build_local_ticker_map()
        high_price_map = {}

        # 당일 수급 요약에서 신고가 정보 수집
        summary = self.get_daily_summary(date, force_sync)
        for m_key in ["KOSPI", "KOSDAQ"]:
            for s_key in ["FOREIGN", "INSTITUTION"]:
                cat_data = summary.get(m_key, {}).get(s_key)
                if cat_data and hasattr(cat_data, 'items'):
                    for rank_item in cat_data.items:
                        if rank_item.high_price_type:
                            high_price_map[rank_item.name] = rank_item.high_price_type

        # 각 항목 보강
        for item in report.items:
            item.ticker = ticker_map.get(item.name)
            if item.name in high_price_map:
                item.entry_tag = high_price_map[item.name]

    def list_available_ceiling_years(self) -> list[str]:
        """조회 가능한 상한가 분석 연도 목록을 반환합니다 (예: 2020~2026).

        Returns:
            List[str]: 가용한 연도 문자열 리스트 (내림차순).
        """
        years = set()

        # 1. 구글 드라이브 파일 목록에서 연도 추출
        if self._storage:
            try:
                files = self._storage.list_files_in_folder("", folder="ceiling")
                for f in files:
                    # '상한가분석(2025년).xlsx' 패턴에서 연도 추출
                    match = re.search(r"\((\d{4})년\)", f["name"])
                    if match:
                        years.add(match.group(1))
            except Exception as e:
                logger.warning(f"[StatisticsService] 드라이브 연도 목록 조회 실패: {e}")

        # 2. 로컬 저장소 파일들에서도 연도 추출 (오프라인 캐시 고려)
        if self._ceiling_repo:
            local_dates = self._ceiling_repo.list_available_dates()
            for d in local_dates:
                years.add(d[:4])

        # 데이터가 아예 없는 경우 현재 연도라도 반환
        if not years:
            years.add(datetime.now().strftime("%Y"))

        return sorted(list(years), reverse=True)

    def list_available_ceiling_dates(self, year: str | None = None) -> list[str]:
        """특정 연도의 상한가 분석 가용 날짜 목록을 반환합니다.

        Args:
            year (Optional[str], optional): 조회할 연도 (YYYY 형식).
                None일 경우 현재 연도를 기준으로 합니다. Defaults to None.

        Returns:
            List[str]: 가용 날짜 문자열 리스트 (YYYY-MM-DD 형식, 내림차순).
        """
        target_year = year if year else datetime.now().strftime("%Y")

        # 1. 로컬 저장소의 날짜 목록 (해당 연도만 필터링)
        all_local = self._ceiling_repo.list_available_dates() if self._ceiling_repo else []
        local_dates = set(d for d in all_local if d.startswith(target_year))

        # 2. 구글 드라이브 엑셀 시트 목록 조회
        drive_dates = set()
        if self._storage:
            try:
                target_year_file = f"상한가분석({target_year}년).xlsx"
                content = self._storage.get_file(target_year_file, folder="ceiling")
                if content:
                    # 시트 목록만 빠르게 읽기 위해 pd.ExcelFile 사용
                    excel = pd.ExcelFile(io.BytesIO(content))
                    for sheet in excel.sheet_names:
                        # YYMMDD 형식을 YYYY-MM-DD로 변환
                        if len(sheet) == 6 and sheet.isdigit():
                            if sheet.startswith(target_year[2:]):
                                formatted = f"20{sheet[:2]}-{sheet[2:4]}-{sheet[4:]}"
                                drive_dates.add(formatted)
            except Exception as e:
                logger.warning(f"[StatisticsService] {target_year}년 드라이브 가용 날짜 조회 실패: {e}")

        # 3. 병합 및 정렬 (최신순)
        return sorted(list(local_dates | drive_dates), reverse=True)
