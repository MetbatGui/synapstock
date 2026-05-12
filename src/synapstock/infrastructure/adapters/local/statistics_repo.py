from pathlib import Path

from synapstock.domain.statistics.models import (
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
    """통계 데이터를 로컬 JSON 파일로 관리하는 저장소."""

    def __init__(self, data_root: str = "data/statistics/netbuy"):
        self.root = Path(data_root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save_daily_ranking(self, ranking: DailyMarketRanking):
        """일별 순위를 저장한다."""
        self.root.mkdir(parents=True, exist_ok=True)
        # 파일명 형식: 2026-04-07_KOSPI_FOREIGN.json
        market_val = ranking.market.value if hasattr(ranking.market, "value") else str(ranking.market)
        subject_val = ranking.subject.value if hasattr(ranking.subject, "value") else str(ranking.subject)
        filename = f"{ranking.date}_{market_val}_{subject_val}.json"
        path = self.root / filename
        with open(path, "w", encoding="utf-8") as f:
            f.write(ranking.model_dump_json(indent=2))

    def load_ranking(self, date: str, market: MarketType, subject: SupplySubject) -> DailyMarketRanking | None:
        """특정 날짜의 순위를 불러온다."""
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
        """데이터가 존재하는 날짜 목록을 반환한다."""
        market_val = market.value if hasattr(market, "value") else str(market)
        subject_val = subject.value if hasattr(subject, "value") else str(subject)
        # 정규 형식(*_KOSPI_FOREIGN.json)과 구형 형식(*MarketType.KOSPI*.json) 모두 매칭 시도
        pattern = f"*{market_val}*{subject_val}*.json"
        files = self.root.glob(pattern)
        # 파일명에서 날짜 부분만 추출 (YYYY-MM-DD)
        return sorted([f.name.split("_")[0] for f in files], reverse=True)

    def get_rankings(self, date: str) -> list[DailyMarketRanking]:
        """특정 날짜의 모든 시장/주체별 순위 리스트를 가져온다."""
        results = []
        for market in MarketType:
            for subject in SupplySubject:
                res = self.load_ranking(date, market, subject)
                if res:
                    results.append(res)
        return results


class LocalCeilingRepository:
    """상한가 분석 데이터를 로컬 JSON 파일로 관리하는 저장소."""

    def __init__(self, data_root: str = "data/statistics/ceiling"):
        self.root = Path(data_root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.metadata_path = self.root / "metadata.json"

    def save_metadata(self, metadata: dict):
        """동기화 메타데이터를 저장한다."""
        self.root.mkdir(parents=True, exist_ok=True)
        import json
        with open(self.metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

    def load_metadata(self) -> dict:
        """동기화 메타데이터를 불러온다."""
        import json
        if not self.metadata_path.exists():
            return {"last_synced_at": "1970-01-01T00:00:00Z", "latest_data_date": ""}
        try:
            with open(self.metadata_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"last_synced_at": "1970-01-01T00:00:00Z", "latest_data_date": ""}

    def save_report(self, report: CeilingAnalysisReport | list[CeilingAnalysisReport]):
        """상한가 분석 리포트(들)를 저장한다."""
        if isinstance(report, list):
            for r in report:
                self._save_single_report(r)
        else:
            self._save_single_report(report)

    def _save_single_report(self, report: CeilingAnalysisReport):
        """단일 리포트를 파일로 저장한다."""
        self.root.mkdir(parents=True, exist_ok=True)
        filename = f"ceiling_{report.end_date}.json"
        path = self.root / filename
        with open(path, "w", encoding="utf-8") as f:
            f.write(report.model_dump_json(indent=2))

    def load_latest_report(self) -> CeilingAnalysisReport | None:
        """가장 최근 날짜의 리포트를 불러온다."""
        dates = self.list_available_dates()
        if not dates:
            return None

        return self.load_report(dates[0])

    def load_report(self, date: str) -> CeilingAnalysisReport | None:
        """특정 날짜의 리포트를 불러온다. (YYYY-MM-DD)"""
        filename = f"ceiling_{date}.json"
        path = self.root / filename
        if not path.exists():
            return None

        with open(path, encoding="utf-8") as f:
            return CeilingAnalysisReport.model_validate_json(f.read())

    def list_available_dates(self) -> list[str]:
        """데이터가 존재하는 리포트 날짜 목록을 반환한다."""
        # ceiling_2026-01-15.json 형식의 파일들 탐색
        files = self.root.glob("ceiling_*.json")
        dates = []
        for f in files:
            try:
                # 'ceiling_' (8자) 이후부터 '.json' 전까지 추출
                date_str = f.name[8:-5]
                dates.append(date_str)
            except Exception:
                continue
        return sorted(dates, reverse=True)


class LocalCapitalIncreaseRepository:
    """유상증자 분석 데이터를 로컬 JSON 파일로 관리하는 저장소."""

    def __init__(self, data_root: str = "data/statistics/capital_increase"):
        self.root = Path(data_root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save_data(self, items: list[PaidInCapitalIncrease]):
        """유상증자 데이터 리스트를 로컬 전용 파일에 저장합니다."""
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / "capital_increase_data.json"
        import json

        with open(path, "w", encoding="utf-8") as f:
            data = [item.model_dump() for item in items]
            json.dump(data, f, indent=2, ensure_ascii=False)

    def load_data(self) -> list[PaidInCapitalIncrease]:
        """로컬에 저장된 유상증자 데이터 리스트를 불러옵니다."""
        path = self.root / "capital_increase_data.json"
        if not path.exists():
            return []

        import json

        with open(path, encoding="utf-8") as f:
            data = json.load(f)
            return [PaidInCapitalIncrease.model_validate(item) for item in data]


class LocalBonusIssueRepository:
    """무상증자 분석 데이터를 로컬 JSON 파일로 관리하는 저장소."""

    def __init__(self, data_root: str = "data/statistics/bonus_issue"):
        self.root = Path(data_root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save_data(self, items: list[BonusIssue]):
        """무상증자 데이터 리스트를 로컬 전용 파일에 저장합니다."""
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / "bonus_issue_data.json"
        import json

        with open(path, "w", encoding="utf-8") as f:
            data = [item.model_dump() for item in items]
            json.dump(data, f, indent=2, ensure_ascii=False)

    def load_data(self) -> list[BonusIssue]:
        """로컬에 저장된 무상증자 데이터 리스트를 불러옵니다."""
        path = self.root / "bonus_issue_data.json"
        if not path.exists():
            return []

        import json

        with open(path, encoding="utf-8") as f:
            data = json.load(f)
            return [BonusIssue.model_validate(item) for item in data]


class LocalConvertibleBondRepository:
    """전환사채(CB) 분석 데이터를 로컬 JSON 파일로 관리하는 저장소."""

    def __init__(self, data_root: str = "data/statistics/convertible_bond"):
        self.root = Path(data_root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save_data(self, items: list[ConvertibleBond]):
        """전환사채 데이터 리스트를 로컬 전용 파일에 저장합니다."""
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / "convertible_bond_data.json"
        import json

        with open(path, "w", encoding="utf-8") as f:
            data = [item.model_dump() for item in items]
            json.dump(data, f, indent=2, ensure_ascii=False)

    def load_data(self) -> list[ConvertibleBond]:
        """로컬에 저장된 전환사채 데이터 리스트를 불러옵니다."""
        path = self.root / "convertible_bond_data.json"
        if not path.exists():
            return []

        import json

        with open(path, encoding="utf-8") as f:
            data = json.load(f)
            return [ConvertibleBond.model_validate(item) for item in data]


class LocalBondWithWarrantsRepository:
    """신주인수권부사채(BW) 분석 데이터를 로컬 JSON 파일로 관리하는 저장소."""

    def __init__(self, data_root: str = "data/statistics/bw"):
        self.root = Path(data_root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save_data(self, items: list[BondWithWarrants]):
        """신주인수권부사채 데이터 리스트를 로컬 전용 파일에 저장합니다."""
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / "bw_data.json"
        import json

        with open(path, "w", encoding="utf-8") as f:
            data = [item.model_dump() for item in items]
            json.dump(data, f, indent=2, ensure_ascii=False)

    def load_data(self) -> list[BondWithWarrants]:
        """로컬에 저장된 신주인수권부사채 데이터 리스트를 불러옵니다."""
        path = self.root / "bw_data.json"
        if not path.exists():
            return []

        import json

        with open(path, encoding="utf-8") as f:
            data = json.load(f)
            return [BondWithWarrants.model_validate(item) for item in data]


class LocalWeeklyChangeRepository:
    """주간 등락률 데이터를 로컬 JSON 파일로 관리하는 저장소."""

    def __init__(self, data_root: str = "data/statistics/weekly_change"):
        self.root = Path(data_root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save_report(self, report: WeeklyChangeReport):
        """주간 등락률 리포트를 저장한다."""
        self.root.mkdir(parents=True, exist_ok=True)
        filename = f"weekly_change_{report.date}.json"
        path = self.root / filename
        with open(path, "w", encoding="utf-8") as f:
            f.write(report.model_dump_json(indent=2))

    def load_report(self, date: str) -> WeeklyChangeReport | None:
        """특정 날짜의 주간 등락률 리포트를 불러온다."""
        filename = f"weekly_change_{date}.json"
        path = self.root / filename
        if not path.exists():
            return None

        with open(path, encoding="utf-8") as f:
            from synapstock.domain.statistics.models import WeeklyChangeReport
            return WeeklyChangeReport.model_validate_json(f.read())

    def list_available_dates(self) -> list[str]:
        """데이터가 존재하는 날짜 목록을 반환한다."""
        files = self.root.glob("weekly_change_*.json")
        dates = []
        for f in files:
            try:
                # 'weekly_change_' (14자) 이후부터 '.json' 전까지 추출
                date_str = f.name[14:-5]
                dates.append(date_str)
            except Exception:
                continue
        return sorted(dates, reverse=True)
