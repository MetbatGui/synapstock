import io
import logging

import pandas as pd

from synapstock.application.services.base_statistics_service import BaseStatisticsService
from synapstock.domain.statistics.models import (
    AnalyzedRankingItem,
    DailyMarketRanking,
    DailyMarketRankingAnalysis,
    MarketType,
    MonthlyMarketStats,
    SupplySubject,
)
from synapstock.infrastructure.adapters.local.cache_manager import LocalCacheManager
from synapstock.infrastructure.parsers.excel import SupplyDemandParser

logger = logging.getLogger(__name__)

class RankingService(BaseStatisticsService[DailyMarketRanking]):
    """거래일/월간 수급 순위 및 분석 전문 서비스."""

    def __init__(self, drive_adapter, folder_id, local_repository):
        super().__init__(drive_adapter, folder_id)
        self.repository = local_repository
        self.parser = SupplyDemandParser()
        self.cache_manager = LocalCacheManager()
        self._daily_cache = {}
        self._monthly_cache = {}

    def get_service_name(self) -> str:
        return "RankingService"

    async def get_daily_ranking(self, date_str: str, market: MarketType = None, subject: SupplySubject = None) -> list[DailyMarketRanking] | DailyMarketRanking | None:
        """로컬 저장소에서 당일 순위를 가져오고, 없으면 동기화합니다.
        
        기존 Facade와의 호환성을 위해 market, subject가 지정되면 단일 객체를 반환합니다.
        """
        cache_key = f"{date_str}_{market}_{subject}"
        if cache_key in self._daily_cache:
            return self._daily_cache[cache_key]

        if market and subject:
            res = self.repository.load_ranking(date_str, market, subject)
            if not res:
                await self.sync_data(date_str)
                res = self.repository.load_ranking(date_str, market, subject)
            if res:
                self._daily_cache[cache_key] = res
            return res

        rankings = self.repository.get_rankings(date_str)
        if not rankings:
            rankings = await self.sync_data(date_str)
        if rankings:
            self._daily_cache[cache_key] = rankings
        return rankings

    async def get_daily_summary(self, date: str) -> dict:
        """해당 날짜의 4가지 조합(코스피/코스닥 x 외국인/기관) 수급 데이터를 요약하여 반환합니다."""
        summary = {
            "KOSPI": {
                "FOREIGN": await self.get_daily_ranking(date, MarketType.KOSPI, SupplySubject.FOREIGN),
                "INSTITUTION": await self.get_daily_ranking(date, MarketType.KOSPI, SupplySubject.INSTITUTION),
            },
            "KOSDAQ": {
                "FOREIGN": await self.get_daily_ranking(date, MarketType.KOSDAQ, SupplySubject.FOREIGN),
                "INSTITUTION": await self.get_daily_ranking(date, MarketType.KOSDAQ, SupplySubject.INSTITUTION),
            }
        }
        return summary

    async def get_monthly_ranking(self, month: str, market: MarketType, subject: SupplySubject) -> MonthlyMarketStats:
        """한 달간의 일별 데이터를 합산하여 월간 누적 수급 순위를 산출합니다."""
        cache_key = f"{month}_{market}_{subject}"
        if cache_key in self._monthly_cache:
            return self._monthly_cache[cache_key]

        available_dates = self.repository.list_available_dates(market, subject)
        target_dates = [d for d in available_dates if d.startswith(month)]

        if not target_dates:
            return MonthlyMarketStats(month=month, market=market, subject=subject, items=[])

        # 일별 데이터 로드
        daily_rankings = []
        for d in target_dates:
            ranking = self.repository.load_ranking(d, market, subject)
            if ranking:
                daily_rankings.append(ranking)

        if not daily_rankings:
            return MonthlyMarketStats(month=month, market=market, subject=subject, items=[])

        # 도메인 모델의 비즈니스 로직을 호출하여 합산 수행
        res = MonthlyMarketStats.aggregate_from_daily(month, daily_rankings)
        self._monthly_cache[cache_key] = res
        return res

    async def sync_data(self, date_str: str | None = None) -> list[DailyMarketRanking]:
        """엑셀 파일에서 순위 데이터를 파싱하고 동기화합니다.
        
        date_str이 없으면 드라이브에서 가장 최신 파일을 찾아 동기화합니다.
        캐시를 확인하여 파일이 변경된 경우에만 다운로드 및 파싱을 수행합니다.
        """
        try:
            if not self.drive_adapter:
                return []

            # 1. 파일 목록 조회 (계층형 구조 지원)
            files = await self.drive_adapter.list_files(self.folder_id)
            if not files:
                logger.warning(f"[{self.get_service_name()}] 드라이브에서 파일을 찾을 수 없습니다.")
                return []

            all_files = []
            year_folders = [f for f in files if "년" in f["name"] and f["mimeType"] == "application/vnd.google-apps.folder"]

            if year_folders:
                # 연도 및 월 폴더 탐색
                target_year = date_str[:4] if date_str else "2026"
                target_month = date_str[5:7] if date_str else ""

                year_folder = next((f for f in year_folders if target_year in f["name"]), year_folders[0])
                logger.info(f"[{self.get_service_name()}] 연도 서브폴더 탐색: {year_folder['name']}")

                sub_items = await self.drive_adapter.list_files_in_folder("", root_id=year_folder["id"])
                month_folders = [f for f in sub_items if "월" in f["name"] and f["mimeType"] == "application/vnd.google-apps.folder"]

                if month_folders:
                    if target_month:
                        month_folder = next((f for f in month_folders if target_month in f["name"]), month_folders[0])
                    else:
                        month_folder = sorted(month_folders, key=lambda x: x["name"], reverse=True)[0]

                    logger.info(f"[{self.get_service_name()}] 월 서브폴더 탐색: {month_folder['name']}")
                    all_files = await self.drive_adapter.list_files_in_folder("", root_id=month_folder["id"])
                else:
                    all_files = sub_items
            else:
                all_files = files

            # 2. 대상 파일 필터링
            if date_str:
                date_pure = date_str.replace("-", "")
                target_files = [f for f in all_files if date_pure in f["name"]]
                if not target_files:
                    logger.warning(f"[{self.get_service_name()}] {date_str} 날짜의 파일을 찾을 수 없습니다.")
                    return []
            else:
                valid_files = [f for f in all_files if f["name"].lower().endswith((".xlsx", ".xls"))]
                if not valid_files:
                    logger.warning(f"[{self.get_service_name()}] 유효한 랭킹 파일을 찾을 수 없습니다.")
                    return []
                target_files = [sorted(valid_files, key=lambda x: x["name"], reverse=True)[0]]

            # 3. 캐시 확인 및 동기화 수행
            all_rankings = []
            needs_sync = False

            for file_info in target_files:
                file_name = file_info["name"]
                modified_time = file_info.get("modifiedTime", "")

                if self.cache_manager.needs_update("ranking", file_name, modified_time):
                    logger.info(f"[{self.get_service_name()}] 업데이트 발견: {file_name} (Modified: {modified_time})")
                    needs_sync = True

                    content = await self.drive_adapter.get_file_by_id(file_info["id"])
                    if not content: continue

                    sheets = pd.read_excel(io.BytesIO(content), sheet_name=None, header=None)
                    for sheet_name in sheets.keys():
                        try:
                            # RankingService에 특화된 파싱 로직 (date_str이 없는 경우 파일명 등에서 추론 필요할 수 있음)
                            rankings = self.parser.parse_summary_table(content, sheet_name, date_str or file_name)
                            all_rankings.extend(rankings)
                        except Exception as e:
                            logger.warning(f"[{self.get_service_name()}] 시트 {sheet_name} 파싱 건너뜀: {e}")

                    self.cache_manager.update_cache_info("ranking", file_name, modified_time, {"file_id": file_info["id"]})
                else:
                    logger.info(f"[{self.get_service_name()}] 캐시가 최신입니다: {file_name}")

            if needs_sync:
                # 저장소에 개별 저장
                for r in all_rankings:
                    self.repository.save_daily_ranking(r)
                logger.info(f"[{self.get_service_name()}] {len(all_rankings)}건의 데이터가 동기화되었습니다.")
                return all_rankings

            return self.repository.get_rankings(date_str)
        except Exception as e:
            logger.error(f"[RankingService] 순위 동기화 실패: {e}", exc_info=True)
            return []

    async def get_analyzed_ranking(self, date, market, subject) -> DailyMarketRankingAnalysis:
        """이전 거래일과 비교하여 순위 변동을 분석합니다."""
        raw = self.repository.load_ranking(date, market, subject)
        if not raw:
            return None

        available_dates = self.repository.list_available_dates(market, subject)
        try:
            current_idx = available_dates.index(date)
        except ValueError:
            analyzed_items = [AnalyzedRankingItem(**item.model_dump()) for item in raw.items]
            return DailyMarketRankingAnalysis(date=date, market=market, subject=subject, items=analyzed_items)

        # 이전 거래일 데이터와 대조 분석
        if current_idx + 1 < len(available_dates):
            prev_date = available_dates[current_idx + 1]
            prev_raw = self.repository.load_ranking(prev_date, market, subject)
            prev_map = {item.name: item.rank for item in prev_raw.items} if prev_raw else {}

            analyzed_items = []
            for item in raw.items:
                prev_rank = prev_map.get(item.name)
                analyzed_items.append(AnalyzedRankingItem(
                    **item.model_dump(),
                    prev_rank=prev_rank,
                    consecutive_days=await self._calculate_consecutive_days(
                        item.name, available_dates[current_idx:], market, subject, limit=11
                    )
                ))
            return DailyMarketRankingAnalysis(date=date, market=market, subject=subject, items=analyzed_items, previous_date=prev_date)

        return DailyMarketRankingAnalysis(date=date, market=market, subject=subject, items=[AnalyzedRankingItem(**it.model_dump()) for it in raw.items])

    async def _calculate_consecutive_days(self, name, dates, market, subject, limit: int = 30) -> int:
        """종목이 연속으로 순위권에 머문 일수를 계산합니다."""
        count = 0
        for d in dates:
            r = self.repository.load_ranking(d, market, subject)
            if r and any(it.name == name for it in r.items):
                count += 1
                if count >= limit:
                    break
            else:
                break
        return count
