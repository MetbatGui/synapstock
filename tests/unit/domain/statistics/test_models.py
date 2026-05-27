
from synapstock.domain.statistics import DailyMarketRanking, MarketType, RankingItem, SupplySubject


def test_create_daily_market_ranking():
    """DailyMarketRanking 모델 생성 및 데이터 검증 테스트."""
    item = RankingItem(rank=1, name="삼성전자", amount=1234567, ticker="005930")

    ranking = DailyMarketRanking(
        date="2024-04-06",
        market=MarketType.KOSPI,
        subject=SupplySubject.FOREIGN,
        items=[item]
    )

    assert ranking.date == "2024-04-06"
    assert ranking.market == "KOSPI"
    assert ranking.subject == "FOREIGN"
    assert len(ranking.items) == 1
    assert ranking.items[0].name == "삼성전자"
    assert ranking.items[0].ticker == "005930"

def test_market_type_enum():
    """MarketType Enum 값이 올바른지 확인."""
    assert MarketType.KOSPI == "KOSPI"
    assert MarketType.KOSDAQ == "KOSDAQ"

def test_supply_subject_enum():
    """SupplySubject Enum 값이 올바른지 확인."""
    assert SupplySubject.FOREIGN == "FOREIGN"
    assert SupplySubject.INSTITUTION == "INSTITUTION"


def test_stock_split_model_normalization():
    """StockSplit 모델의 Pydantic Validator 작동 및 데이터 정규화 검증."""
    from synapstock.domain.statistics import StockSplit

    # 1. 일반적인 한글 컬럼 매핑 및 포맷 정규화 테스트
    split_data = {
        "회사명": "삼성전자",
        "시장": "KOSPI",
        "공시구분": "공시",
        "배정기준일": "2024.12.12",
        "이사회결의일": "2024.12.12 00:00:00",
        "접수번호": "20241212801081",
        "원접수번호": "2.0241212e+13",
        "발행주식수(이전)": "20520649.0",
        "발행주식수(이후)": 102603245.0,
        "분할비율": "5.0",
        "신주상장예정일": "2025-02-27",
        "주총결의일": "2024-12-12"
    }

    model = StockSplit(**split_data)

    assert model.company_name == "삼성전자"
    assert model.market == "KOSPI"
    assert model.disclosure_type == "공시"
    assert model.base_date == "2024-12-12"  # . -> - 변환
    assert model.board_resolution_date == "2024-12-12"  # 시간 제거 및 . -> - 변환
    assert model.receipt_no == "20241212801081"
    assert model.original_receipt_no == "20241212000000"  # float parsing check
    assert model.prev_shares == 20520649
    assert model.post_shares == 102603245
    assert model.split_ratio == 5.0
    assert model.listing_date == "2025-02-27"
    assert model.general_meeting_date == "2024-12-12"

    # 2. NaN 및 빈 값(None) 처리 검증 (엣지 케이스)
    edge_data = {
        "회사명": "엣지컴퍼니",
        "시장": None,
        "공시구분": "nan",
        "배정기준일": "2026.01.01",
        "이사회결의일": "NaN",
        "접수번호": "20260101900123",
        "원접수번호": None,
        "발행주식수(이전)": None,
        "발행주식수(이후)": "NaN",
        "분할비율": None,
        "신주상장예정일": "",
        "주총결의일": None
    }

    model_edge = StockSplit(**edge_data)

    assert model_edge.market is None
    assert model_edge.disclosure_type is None
    assert model_edge.board_resolution_date is None
    assert model_edge.original_receipt_no is None
    assert model_edge.prev_shares is None
    assert model_edge.post_shares is None
    assert model_edge.split_ratio is None
    assert model_edge.listing_date is None
    assert model_edge.general_meeting_date is None


def test_stock_split_manifest_model():
    """StockSplitManifest 모델 생성 및 데이터 검증."""
    from synapstock.domain.statistics import StockSplitManifest

    manifest_data = {
        "manifest_version": "1.0.0",
        "last_updated": "2026-05-27T14:21:56.077970",
        "total_records": 103,
        "supported_years": ["2024", "2025", "2026"],
        "years_index": {
            "2026": ["20260428900678", "20260427901109"]
        }
    }

    manifest = StockSplitManifest(**manifest_data)
    assert manifest.manifest_version == "1.0.0"
    assert manifest.total_records == 103
    assert "2026" in manifest.years_index
    assert manifest.years_index["2026"] == ["20260428900678", "20260427901109"]

