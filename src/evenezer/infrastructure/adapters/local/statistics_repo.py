from pathlib import Path

from evenezer.domain.statistics.models import (
    BondWithWarrants,
    BonusIssue,
    CeilingAnalysisReport,
    ConvertibleBond,
    DailyMarketRanking,
    MarketType,
    PaidInCapitalIncrease,
    SupplySubject,
    WeeklyChangeReport,
)


class LocalStatisticsRepository:
    """수급 순위 및 신규 상장 등의 통계 데이터를 로컬 JSON 파일로 관리하는 저장소입니다."""

    def __init__(self, data_root: str = "data/statistics/netbuy"):
        """LocalStatisticsRepository를 초기화합니다.

        Args:
            data_root: 수급 순위 JSON 파일이 저장될 루트 디렉터리 경로.
        """
        self.root = Path(data_root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save_new_listings(self, items: list, year: str = "2026"):
        """신규 상장 데이터 목록을 연도별 로컬 JSON 파일에 영속화합니다.

        Args:
            items: 저장할 신규 상장 데이터 객체 목록.
            year: 대상 연도 구분 문자열.
        """
        folder = self.root.parent / "new_listing"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"new_listing_data_{year}.json"
        import json
        with open(path, "w", encoding="utf-8") as f:
            # Pydantic 모델 직렬화 지원
            data = [item.model_dump() if hasattr(item, "model_dump") else item for item in items]
            json.dump(data, f, indent=2, ensure_ascii=False)

    def get_new_listings(self, year: str = "2026") -> list:
        """로컬 파일로부터 특정 연도의 신규 상장 데이터 목록을 로드하여 반환합니다.

        Args:
            year: 대상 연도 구분 문자열.

        Returns:
            로딩된 NewListing 도메인 모델 목록. 파일이 없거나 예외 시 빈 목록.
        """
        folder = self.root.parent / "new_listing"
        path = folder / f"new_listing_data_{year}.json"
        if not path.exists():
            return []
        import json
        import logging
        local_logger = logging.getLogger(__name__)

        from evenezer.domain.statistics.models import NewListing
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
                return [NewListing.model_validate(item) for item in data]
        except Exception as e:
            local_logger.error(f"[LocalStatisticsRepository] '{path.name}' 로드 중 예외 발생: {e}", exc_info=True)
            return []

    def save_daily_ranking(self, ranking: DailyMarketRanking):
        """특정 날짜의 일별 수급 거래 순위 데이터를 규격화된 파일명으로 저장합니다.

        Args:
            ranking: 저장할 일별 수급 순위 모델.
        """
        self.root.mkdir(parents=True, exist_ok=True)
        # 파일명 형식: 2026-04-07_KOSPI_FOREIGN.json
        market_val = ranking.market.value if hasattr(ranking.market, "value") else str(ranking.market)
        subject_val = ranking.subject.value if hasattr(ranking.subject, "value") else str(ranking.subject)
        filename = f"{ranking.date}_{market_val}_{subject_val}.json"
        path = self.root / filename
        with open(path, "w", encoding="utf-8") as f:
            f.write(ranking.model_dump_json(indent=2))

    def load_ranking(self, date: str, market: MarketType, subject: SupplySubject) -> DailyMarketRanking | None:
        """지정된 일자, 시장 유형, 투자 주체 조건에 해당하는 수급 순위 데이터를 로컬 파일에서 로드합니다.

        Args:
            date: 조회 기준일 문자열 ('YYYY-MM-DD').
            market: 대상 시장 (KOSPI 또는 KOSDAQ).
            subject: 투자 주체 (FOREIGN, INSTITUTION 등).

        Returns:
            복원 완료된 DailyMarketRanking 객체. 매칭 파일이 없으면 None.
        """
        market_val = market.value if hasattr(market, "value") else str(market)
        subject_val = subject.value if hasattr(subject, "value") else str(subject)

        # 1. 정규 형식 시도 (*_KOSPI_FOREIGN.json)
        filename = f"{date}_{market_val}_{subject_val}.json"
        path = self.root / filename

        # 2. 존재하지 않으면 유연한 검색 시도
        if not path.exists():
            pattern = f"{date}*{market_val}*{subject_val}*.json"
            files = list(self.root.glob(pattern))
            if not files:
                return None
            path = files[0]

        with open(path, encoding="utf-8") as f:
            return DailyMarketRanking.model_validate_json(f.read())

    def list_available_dates(self, market: MarketType, subject: SupplySubject) -> list[str]:
        """지정된 시장 유형과 투자 주체 조건의 수급 파일이 존재하는 모든 일자 목록을 정렬하여 반환합니다.

        Args:
            market: 대상 시장.
            subject: 투자 주체.

        Returns:
            정렬된 일자 문자열 목록.
        """
        market_val = market.value if hasattr(market, "value") else str(market)
        subject_val = subject.value if hasattr(subject, "value") else str(subject)
        pattern = f"*{market_val}*{subject_val}*.json"
        files = self.root.glob(pattern)
        return sorted([f.name.split("_")[0] for f in files], reverse=True)

    def get_rankings(self, date: str) -> list[DailyMarketRanking]:
        """특정 날짜의 모든 시장 및 투자 주체 조합에 대응하는 수급 순위 데이터 목록을 반환합니다.

        Args:
            date: 기준 일자 문자열.

        Returns:
            로딩 가능한 모든 DailyMarketRanking 인스턴스들의 목록.
        """
        results = []
        for market in MarketType:
            for subject in SupplySubject:
                res = self.load_ranking(date, market, subject)
                if res:
                    results.append(res)
        return results


class LocalCeilingRepository:
    """상한가 종목 분석 데이터를 로컬 JSON 파일로 관리하는 저장소입니다."""

    def __init__(self, data_root: str = "data/statistics/ceiling"):
        """LocalCeilingRepository를 초기화합니다.

        Args:
            data_root: 상한가 데이터 파일이 저장되는 디렉터리 경로.
        """
        self.root = Path(data_root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.metadata_path = self.root / "metadata.json"

    def save_metadata(self, metadata: dict):
        """구글 드라이브 동기화 관련 메타데이터를 저장합니다.

        Args:
            metadata: 동기화 시각 및 최종 데이터 날짜 정보를 포함하는 딕셔너리.
        """
        self.root.mkdir(parents=True, exist_ok=True)
        import json
        with open(self.metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

    def load_metadata(self) -> dict:
        """동기화 관련 메타데이터를 로드합니다. 파일이 없을 경우 기본 구성 사양을 반환합니다.

        Returns:
            동기화 메타데이터를 담은 딕셔너리.
        """
        import json
        if not self.metadata_path.exists():
            return {"last_synced_at": "1970-01-01T00:00:00Z", "latest_data_date": ""}
        try:
            with open(self.metadata_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"last_synced_at": "1970-01-01T00:00:00Z", "latest_data_date": ""}

    def save_report(self, report: CeilingAnalysisReport | list[CeilingAnalysisReport]):
        """상한가 분석 리포트 또는 리포트 목록을 파일로 영속화합니다.

        Args:
            report: 저장할 단일 혹은 복수의 CeilingAnalysisReport 인스턴스.
        """
        if isinstance(report, list):
            for r in report:
                self._save_single_report(r)
        else:
            self._save_single_report(report)

    def _save_single_report(self, report: CeilingAnalysisReport):
        """단일 상한가 분석 리포트를 날짜 기반 파일로 영속화합니다."""
        self.root.mkdir(parents=True, exist_ok=True)
        filename = f"ceiling_{report.end_date}.json"
        path = self.root / filename
        with open(path, "w", encoding="utf-8") as f:
            f.write(report.model_dump_json(indent=2))

    def load_latest_report(self) -> CeilingAnalysisReport | None:
        """로컬 저장소에 보관된 가장 최근 날짜의 상한가 분석 리포트를 반환합니다.

        Returns:
            최신 CeilingAnalysisReport 객체, 리포트가 전혀 없을 경우 None.
        """
        dates = self.list_available_dates()
        if not dates:
            return None

        return self.load_report(dates[0])

    def load_report(self, date: str) -> CeilingAnalysisReport | None:
        """특정 날짜의 상한가 분석 리포트를 조회하여 반환합니다.

        Args:
            date: 기준 일자 ('YYYY-MM-DD').

        Returns:
            지정된 날짜의 CeilingAnalysisReport 객체. 존재하지 않으면 None.
        """
        filename = f"ceiling_{date}.json"
        path = self.root / filename
        if not path.exists():
            return None

        with open(path, encoding="utf-8") as f:
            return CeilingAnalysisReport.model_validate_json(f.read())

    def list_available_dates(self) -> list[str]:
        """상한가 리포트 데이터 파일이 존재하는 날짜 목록을 역순으로 정렬하여 반환합니다.

        Returns:
            날짜 문자열 목록.
        """
        files = self.root.glob("ceiling_*.json")
        dates = []
        for f in files:
            try:
                date_str = f.name[8:-5]
                dates.append(date_str)
            except Exception:
                continue
        return sorted(dates, reverse=True)


class LocalCapitalIncreaseRepository:
    """유상증자 분석 데이터를 로컬 JSON 파일로 관리하는 저장소입니다."""

    def __init__(self, data_root: str = "data/statistics/capital_increase"):
        """LocalCapitalIncreaseRepository를 초기화합니다.

        Args:
            data_root: 유상증자 분석 결과가 저장되는 디렉터리 경로.
        """
        self.root = Path(data_root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save_data(self, items: list[PaidInCapitalIncrease]):
        """유상증자 내역 데이터 목록을 통합 로컬 파일로 저장합니다.

        Args:
            items: 유상증자 도메인 인스턴스 목록.
        """
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / "capital_increase_data.json"
        import json

        with open(path, "w", encoding="utf-8") as f:
            data = [item.model_dump() for item in items]
            json.dump(data, f, indent=2, ensure_ascii=False)

    def load_data(self) -> list[PaidInCapitalIncrease]:
        """로컬 파일로부터 유상증자 데이터 목록을 반환합니다.

        Returns:
            PaidInCapitalIncrease 도메인 모델 목록.
        """
        path = self.root / "capital_increase_data.json"
        if not path.exists():
            return []

        import json

        with open(path, encoding="utf-8") as f:
            data = json.load(f)
            return [PaidInCapitalIncrease.model_validate(item) for item in data]


class LocalBonusIssueRepository:
    """무상증자 분석 데이터를 로컬 JSON 파일로 관리하는 저장소입니다."""

    def __init__(self, data_root: str = "data/statistics/bonus_issue"):
        """LocalBonusIssueRepository를 초기화합니다.

        Args:
            data_root: 무상증자 분석 결과가 저장되는 디렉터리 경로.
        """
        self.root = Path(data_root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save_data(self, items: list[BonusIssue]):
        """무상증자 내역 데이터 목록을 통합 로컬 파일로 저장합니다.

        Args:
            items: 무상증자 도메인 인스턴스 목록.
        """
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / "bonus_issue_data.json"
        import json

        with open(path, "w", encoding="utf-8") as f:
            data = [item.model_dump() for item in items]
            json.dump(data, f, indent=2, ensure_ascii=False)

    def load_data(self) -> list[BonusIssue]:
        """로컬 파일로부터 무상증자 데이터 목록을 반환합니다.

        Returns:
            BonusIssue 도메인 모델 목록.
        """
        path = self.root / "bonus_issue_data.json"
        if not path.exists():
            return []

        import json

        with open(path, encoding="utf-8") as f:
            data = json.load(f)
            return [BonusIssue.model_validate(item) for item in data]


class LocalConvertibleBondRepository:
    """전환사채(CB) 분석 데이터를 로컬 JSON 파일로 관리하는 저장소입니다."""

    def __init__(self, data_root: str = "data/statistics/convertible_bond"):
        """LocalConvertibleBondRepository를 초기화합니다.

        Args:
            data_root: 전환사채 분석 결과가 저장되는 디렉터리 경로.
        """
        self.root = Path(data_root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save_data(self, items: list[ConvertibleBond]):
        """전환사채 데이터 목록을 통합 로컬 파일로 저장합니다.

        Args:
            items: 전환사채 도메인 인스턴스 목록.
        """
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / "convertible_bond_data.json"
        import json

        with open(path, "w", encoding="utf-8") as f:
            data = [item.model_dump() for item in items]
            json.dump(data, f, indent=2, ensure_ascii=False)

    def load_data(self) -> list[ConvertibleBond]:
        """로컬 파일로부터 전환사채 데이터 목록을 반환합니다.

        Returns:
            ConvertibleBond 도메인 모델 목록.
        """
        path = self.root / "convertible_bond_data.json"
        if not path.exists():
            return []

        import json

        with open(path, encoding="utf-8") as f:
            data = json.load(f)
            return [ConvertibleBond.model_validate(item) for item in data]


class LocalBondWithWarrantsRepository:
    """신주인수권부사채(BW) 분석 데이터를 로컬 JSON 파일로 관리하는 저장소입니다."""

    def __init__(self, data_root: str = "data/statistics/bw"):
        """LocalBondWithWarrantsRepository를 초기화합니다.

        Args:
            data_root: 신주인수권부사채 분석 결과가 저장되는 디렉터리 경로.
        """
        self.root = Path(data_root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save_data(self, items: list[BondWithWarrants]):
        """신주인수권부사채 데이터 목록을 통합 로컬 파일로 저장합니다.

        Args:
            items: 신주인수권부사채 도메인 인스턴스 목록.
        """
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / "bw_data.json"
        import json

        with open(path, "w", encoding="utf-8") as f:
            data = [item.model_dump() for item in items]
            json.dump(data, f, indent=2, ensure_ascii=False)

    def load_data(self) -> list[BondWithWarrants]:
        """로컬 파일로부터 신주인수권부사채 데이터 목록을 반환합니다.

        Returns:
            BondWithWarrants 도메인 모델 목록.
        """
        path = self.root / "bw_data.json"
        if not path.exists():
            return []

        import json

        with open(path, encoding="utf-8") as f:
            data = json.load(f)
            return [BondWithWarrants.model_validate(item) for item in data]


class LocalWeeklyChangeRepository:
    """주간 등락률 리포트 데이터를 로컬 계층형 폴더 구조의 JSON 파일로 관리하는 저장소입니다."""

    def __init__(self, data_root: str = "data/statistics/weekly_change"):
        """LocalWeeklyChangeRepository를 초기화합니다.

        Args:
            data_root: 주간 등락률 리포트 파일들이 저장되는 루트 디렉터리.
        """
        self.root = Path(data_root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _get_report_path(
        self,
        date_str: str,
        year: int | None = None,
        month: int | None = None,
        date_range: str | None = None,
    ) -> Path:
        """지정된 날짜 및 기간 특성에 대응하는 물리적 리포트 파일 저장 경로를 연월 기반 디렉토리 구조로 보정하여 반환합니다.

        Args:
            date_str: 조회 기준 일자.
            year: 연도 정보.
            month: 월 정보.
            date_range: 주간 거래 기간 범위 문자열 (예: '0511~0515').

        Returns:
            연월 구조가 고려된 최종 리포트 Path 객체.
        """
        if not year or not month:
            if len(date_str) >= 10:
                year = int(date_str[:4])
                month = int(date_str[5:7])

        # 파일명 결정: date_range가 있으면 사용, 없으면 date_str 사용
        filename_part = date_range if date_range else date_str

        if year and month:
            folder = self.root / f"{year}년" / f"{month:02d}월"
            folder.mkdir(parents=True, exist_ok=True)
            return folder / f"weekly_change_{filename_part}.json"

        return self.root / f"weekly_change_{filename_part}.json"

    def save_report(self, report: WeeklyChangeReport):
        """주간 등락률 리포트를 기간 속성을 고려한 경로에 파일로 저장합니다.

        Args:
            report: 저장할 WeeklyChangeReport 도메인 인스턴스.
        """
        path = self._get_report_path(report.date, report.year, report.month, report.date_range)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(report.model_dump_json(indent=2))

    def load_report(self, date: str) -> WeeklyChangeReport | None:
        """지정된 일자가 포함되어 있거나 매칭되는 주간 등락률 리포트를 로드하여 복원합니다.

        Args:
            date: 조회할 날짜 문자열 ('YYYY-MM-DD').

        Returns:
            복원 완료된 WeeklyChangeReport 인스턴스. 해당 파일이 없거나 불일치 시 None.
        """
        # 1. 모든 하위 폴더에서 weekly_change_*.json 파일을 찾음
        files = list(self.root.rglob("weekly_change_*.json"))

        # 2. 날짜(예: 0515)가 파일명에 포함되어 있거나, 내부 데이터를 로드해서 확인
        target_date_short = date.replace("-", "")[4:] # '2026-05-15' -> '0515'

        for path in files:
            # 파일명에 0515가 포함되어 있는지 단순 체크 (예: 0511~0515)
            if target_date_short in path.name or date in path.name:
                with open(path, encoding="utf-8") as f:
                    from evenezer.domain.statistics.models import WeeklyChangeReport
                    report = WeeklyChangeReport.model_validate_json(f.read())
                    if report.date == date:
                        return report
        return None

    def list_available_dates(self) -> list[str]:
        """로컬 저장소에 저장된 모든 주간 리포트들의 유효 기준일 목록을 중복 제거 및 정렬하여 반환합니다.

        Returns:
            정렬된 기준 날짜 목록.
        """
        files = self.root.rglob("weekly_change_*.json")
        dates = []
        from evenezer.domain.statistics.models import WeeklyChangeReport
        for f in files:
            try:
                with open(f, encoding="utf-8") as json_file:
                    report = WeeklyChangeReport.model_validate_json(json_file.read())
                    dates.append(report.date)
            except Exception:
                continue
        return sorted(list(set(dates)), reverse=True)
