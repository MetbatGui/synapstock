import logging

from evenezer.application.services.base_statistics_service import BaseStatisticsService
from evenezer.domain.statistics.models import NewListing
from evenezer.infrastructure.parsers.excel.base import BaseExcelParser
from evenezer.infrastructure.persistence import new_listing_db_query
from evenezer.infrastructure.persistence.yearly_db_sync import YearlyDbSync

logger = logging.getLogger(__name__)

# 생산자 DB의 일부 컬럼은 원본 텍스트 형식 그대로 저장돼 있다(예: 기관경쟁률="650:1",
# 유통가능물량(%)="32.33%") - 실 Drive 데이터로 확인함. BaseExcelParser.to_int/to_float가
# 이미 이 형식들을 다루므로(정규식으로 숫자만 추출, "650:1"은 ":" 앞부분만 취함) 새로
# 만들지 않고 그대로 재사용한다.
_to_int = BaseExcelParser.to_int
_to_float = BaseExcelParser.to_float
_to_str = BaseExcelParser.to_str


def _row_to_new_listing(row: dict) -> NewListing:
    """stocks 테이블의 한글 컬럼 딕셔너리를 NewListing 도메인 모델로 매핑한다.

    new_stock_crawler의 DataFrameMapper.COLUMN_MAPPING을 그대로 따른다.
    ticker/note는 생산자 스키마에 없는 필드라 항상 빈 값(기존 Excel 파서와
    동일한 동작 - 원래도 채워진 적 없었다).
    """
    return NewListing(
        listing_date=_to_str(row.get("상장일")),
        name=_to_str(row.get("종목명")),
        market=_to_str(row.get("시장구분")),
        sector=_to_str(row.get("업종")),
        face_value=_to_int(row.get("액면가")),
        hope_price=_to_str(row.get("희망공모가액")),
        offer_price=_to_int(row.get("확정공모가")),
        lead_manager=_to_str(row.get("주간사")),
        institutional_competition=_to_float(row.get("기관경쟁률")),
        employee_shares=_to_int(row.get("우리사주조합")),
        inst_shares=_to_int(row.get("기관투자자")),
        retail_shares=_to_int(row.get("일반청약자")),
        float_shares_pct=_to_float(row.get("유통가능물량(%)")),
        float_shares_vol=_to_int(row.get("유통가능물량(주)")),
        total_offer_shares=_to_int(row.get("총공모주식수")),
        offer_amount=_to_int(row.get("공모금액(백만원)")),
        revenue=_to_int(row.get("매출액(백만원)")),
        ebt=_to_int(row.get("법인세비용차감전(백만원)")),
        net_income=_to_int(row.get("순이익(백만원)")),
        capital=_to_int(row.get("자본금(백만원)")),
        listing_day_open=_to_int(row.get("시가")),
        listing_day_high=_to_int(row.get("고가")),
        listing_day_low=_to_int(row.get("저가")),
        listing_day_close=_to_int(row.get("종가")),
        listing_day_change_pct=_to_float(row.get("수익률(%)")),
    )


class NewListingService(BaseStatisticsService[NewListing]):
    """신규 상장(IPO) 분석 전문 서비스.

    new_stock_crawler가 발행하는 SQLite SSOT DB({year}.db)를 로컬로 구독해
    조회한다 (docs/db_ssot_consumer_sync.md 참고).
    """

    def __init__(self, drive_adapter, folder_id, local_repository, db_sync: YearlyDbSync | None = None):
        super().__init__(drive_adapter, folder_id)
        self.repository = local_repository
        self.db_sync = db_sync or YearlyDbSync(
            drive_adapter=drive_adapter,
            data_root="data/statistics/new_listing/db",
            folder_name="new_listing",
            subfolder="db",
            filename_for_year=lambda year: f"{year}.db",
            required_tables={"stocks"},
        )

    def get_service_name(self) -> str:
        return "NewListingService"

    async def get_data(self, year: str, force_sync: bool = False) -> list[NewListing]:
        """로컬에서 데이터를 조회하고, 없거나 force_sync=True이면 DB를 동기화합니다."""
        if not force_sync:
            items = self.repository.get_new_listings(year)
            if items:
                return items

        return await self.sync_data(year, force=force_sync)

    async def sync_data(self, year: str, force: bool = False) -> list[NewListing]:
        """SSOT DB를 최신 상태로 동기화하고 해당 연도의 전체 종목을 조립합니다."""
        try:
            if not self.drive_adapter:
                return []

            db_path = await self.db_sync.ensure_db(int(year), force=force)
            if not db_path:
                return []

            rows = new_listing_db_query.fetch_listings(db_path)
            listings = [_row_to_new_listing(r) for r in rows]

            if listings:
                self.repository.save_new_listings(listings, year=year)
            return listings

        except Exception as e:
            logger.error(f"[{self.get_service_name()}] 동기화 실패: {e}", exc_info=True)
            return []
