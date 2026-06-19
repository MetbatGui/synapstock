import io
import logging

import pandas as pd

from evenezer.application.services.base_statistics_service import BaseStatisticsService
from evenezer.domain.statistics.models import (
    AnalyzedRankingItem,
    DailyMarketRanking,
    DailyMarketRankingAnalysis,
    MarketType,
    MonthlyMarketStats,
    SupplySubject,
)
from evenezer.infrastructure.adapters.local.cache_manager import LocalCacheManager
from evenezer.infrastructure.parsers.excel import SupplyDemandParser

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
        """해당 날짜의 4가지 조합(코스피/코스닥 x 외국인/기관) 수급 분석 데이터를 요약하여 반환합니다."""
        summary = {
            "KOSPI": {
                "FOREIGN": await self.get_analyzed_ranking(date, MarketType.KOSPI, SupplySubject.FOREIGN),
                "INSTITUTION": await self.get_analyzed_ranking(date, MarketType.KOSPI, SupplySubject.INSTITUTION),
            },
            "KOSDAQ": {
                "FOREIGN": await self.get_analyzed_ranking(date, MarketType.KOSDAQ, SupplySubject.FOREIGN),
                "INSTITUTION": await self.get_analyzed_ranking(date, MarketType.KOSDAQ, SupplySubject.INSTITUTION),
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
        """지정된 폴더 구조에서 특정 엑셀 파일을 찾아 누락된 날짜(시트)를 모두 동기화합니다."""
        try:
            if not self.drive_adapter:
                return []

            # 1. 고정된 폴더 구조 탐색 (현재 연도 기준)
            from datetime import datetime
            now = datetime.now()
            current_year = now.year

            # 1.1 대상 엑셀 파일 탐색
            target_file = await self._find_target_excel_file(current_year)
            if not target_file:
                return []

            # 1.2 파일 수정 날짜 체크 (자동 동기화 판단)
            modified_time = target_file.get("modifiedTime", "")
            needs_sync = self.cache_manager.needs_update("ranking", target_file["name"], modified_time)

            if not needs_sync:
                # 수정 날짜가 동일하면 더 이상 진행할 필요 없음
                return self._get_fallback_rankings(date_str)

            logger.info(f"[{self.get_service_name()}] 파일 업데이트 감지 ({modified_time}). 신규 데이터 확인을 시작합니다.")

            # 2. 파일 다운로드 및 시트 목록 확인
            logger.info(f"[{self.get_service_name()}] 대상 파일 다운로드 중: {target_file['name']}")
            content = await self.drive_adapter.get_file_by_id(target_file["id"])
            if not content:
                return []

            # 3. 동기화할 날짜 결정
            # 로컬에 이미 존재하는 날짜는 건너뜀 (과거 시트는 변경될 이유가 거의 없으므로 신규 추가만 수행)
            existing_dates = set(self.repository.list_available_dates(MarketType.KOSPI, SupplySubject.FOREIGN))
            all_rankings = self._sync_new_sheets(content, current_year, existing_dates)

            return self._post_sync_process(all_rankings, target_file, modified_time, needs_sync, date_str)

        except Exception as e:
            logger.error(f"[{self.get_service_name()}] 순위 동기화 실패: {e}", exc_info=True)
            return []

    def _post_sync_process(
        self,
        all_rankings: list[DailyMarketRanking],
        target_file: dict,
        modified_time: str,
        needs_sync: bool,
        date_str: str | None
    ) -> list[DailyMarketRanking]:
        """동기화 성공 이후의 후처리 작업 및 캐시 갱신을 수행하고 랭킹 목록을 반환합니다."""
        if len(all_rankings) > 0 or needs_sync:
            if len(all_rankings) > 0:
                newly_synced_count = len(set(r.date for r in all_rankings))
                logger.info(f"[{self.get_service_name()}] 총 {newly_synced_count}일치 데이터가 새로 추가되었습니다.")

            # 캐시 매니저 업데이트 (수정 날짜 기록)
            self.cache_manager.update_cache_info(
                "ranking", target_file["name"], modified_time, {"file_id": target_file["id"]}
            )

            if not all_rankings and date_str:
                return self.repository.get_rankings(date_str)
            return all_rankings

        # 새로 동기화된 게 없으면 가장 최근 데이터 반환
        return self._get_fallback_rankings(date_str)

    async def _find_target_excel_file(self, current_year: int) -> dict | None:
        """현재 연도 기준에 따라 수급 엑셀 파일 정보를 탐색하여 반환합니다."""
        target_year = f"{current_year}년"
        target_subfolder = "일별수급정리표"
        target_filename = f"{current_year}일별수급순위정리표.xlsx"

        # 1. 연도 폴더 찾기
        root_files = await self.drive_adapter.list_files_in_folder("", folder="sd")
        year_folder = next((f for f in root_files if target_year in f["name"]), None)
        if not year_folder:
            logger.warning(f"[{self.get_service_name()}] '{target_year}' 폴더를 찾을 수 없습니다.")
            return None

        # 2. 서브 폴더 찾기
        year_items = await self.drive_adapter.list_files_in_folder("", root_id=year_folder["id"], folder="sd")
        sub_folder = next((f for f in year_items if target_subfolder in f["name"]), None)
        if not sub_folder:
            logger.warning(f"[{self.get_service_name()}] '{target_subfolder}' 폴더를 찾을 수 없습니다.")
            return None

        # 3. 대상 파일 찾기
        sub_items = await self.drive_adapter.list_files_in_folder("", root_id=sub_folder["id"], folder="sd")
        target_file = next((f for f in sub_items if target_filename in f["name"]), None)
        if not target_file:
            logger.warning(f"[{self.get_service_name()}] '{target_filename}' 파일을 찾을 수 없습니다.")
            return None

        return target_file

    def _sync_new_sheets(self, excel_content: bytes, current_year: int, existing_dates: set[str]) -> list[DailyMarketRanking]:
        """엑셀 바이너리에서 누락된 MMDD 시트들을 파싱하여 영속화하고 전체 순위 리스트를 반환합니다."""
        xl = pd.ExcelFile(io.BytesIO(excel_content))
        sheet_names = xl.sheet_names
        all_rankings = []

        for sheet_name in sheet_names:
            # 시트 이름은 오직 MMDD 형식만 허용 (예: 0102)
            sheet_name = sheet_name.strip()
            if len(sheet_name) == 4 and sheet_name.isdigit():
                date_norm = f"{current_year}-{sheet_name[:2]}-{sheet_name[2:]}"
            else:
                continue

            if date_norm not in existing_dates:
                logger.info(f"[{self.get_service_name()}] 신규 날짜 발견, 동기화 시작: {date_norm} (시트: {sheet_name})")
                try:
                    rankings = self.parser.parse_summary_table(excel_content, sheet_name, date_norm)
                    if rankings:
                        for r in rankings:
                            self.repository.save_daily_ranking(r)
                        all_rankings.extend(rankings)
                except Exception as e:
                    logger.error(f"[{self.get_service_name()}] 시트 {sheet_name} 파싱 실패: {e}")

        return all_rankings

    def _get_fallback_rankings(self, date_str: str | None) -> list[DailyMarketRanking]:
        """새로 동기화된 내용이 없는 상황에서, 최선의 로컬 순위 데이터를 조회하여 반환합니다."""
        if not date_str:
            dates = self.repository.list_available_dates(MarketType.KOSPI, SupplySubject.FOREIGN)
            if dates:
                date_str = dates[0]
        return self.repository.get_rankings(date_str) if date_str else []

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
