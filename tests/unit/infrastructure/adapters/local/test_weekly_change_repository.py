import pytest

from evenezer.domain.statistics.models import WeeklyChangeReport
from evenezer.infrastructure.adapters.local.statistics_repo import LocalWeeklyChangeRepository


def make_weekly_report(date, week_num, year=2026, month=8, week_of_month=4, date_range=None):
    return WeeklyChangeReport(
        date=date,
        year=year,
        month=month,
        week_of_month=week_of_month,
        week_num=week_num,
        date_range=date_range,
        items=[],
        is_monthly=False,
    )


def make_monthly_report(date, month, year=2026, date_range=None):
    return WeeklyChangeReport(
        date=date,
        year=year,
        month=month,
        week_of_month=0,
        week_num=0,
        date_range=date_range,
        items=[],
        is_monthly=True,
    )


@pytest.fixture
def repo(tmp_path):
    return LocalWeeklyChangeRepository(data_root=str(tmp_path))


def test_save_and_load_report(repo):
    report = make_weekly_report("2026-08-27", week_num=35)
    repo.save_report(report)

    loaded = repo.load_report("2026-08-27")
    assert loaded is not None
    assert loaded.date == "2026-08-27"


def test_resaving_same_week_with_newer_date_removes_stale_snapshot(repo):
    """진행 중인 주가 하루 더 지나 last_trading_day가 갱신되면, 이전 날짜의 캐시는 제거되어야 한다."""
    stale = make_weekly_report("2026-08-26", week_num=35, date_range="0824~0826")
    repo.save_report(stale)

    fresh = make_weekly_report("2026-08-27", week_num=35, date_range="0824~0827")
    repo.save_report(fresh)

    assert repo.load_report("2026-08-26") is None
    assert repo.load_report("2026-08-27") is not None

    dates = repo.list_available_dates()
    assert dates == ["2026-08-27"]


def test_resaving_different_week_does_not_remove_other_weeks(repo):
    week34 = make_weekly_report("2026-08-21", week_num=34)
    repo.save_report(week34)

    week35 = make_weekly_report("2026-08-27", week_num=35)
    repo.save_report(week35)

    assert repo.load_report("2026-08-21") is not None
    assert repo.load_report("2026-08-27") is not None
    assert sorted(repo.list_available_dates()) == ["2026-08-21", "2026-08-27"]


def test_resaving_same_week_number_different_year_does_not_collide(repo):
    """연도가 다르면 week_num이 같아도 별개 스냅샷으로 유지되어야 한다."""
    last_year = make_weekly_report("2025-08-29", week_num=35, year=2025)
    repo.save_report(last_year)

    this_year = make_weekly_report("2026-08-27", week_num=35, year=2026)
    repo.save_report(this_year)

    assert repo.load_report("2025-08-29") is not None
    assert repo.load_report("2026-08-27") is not None


def test_monthly_resave_with_newer_date_removes_stale_snapshot(repo):
    stale = make_monthly_report("2026-08-26", month=8, date_range="0801~0826")
    repo.save_report(stale)

    fresh = make_monthly_report("2026-08-27", month=8, date_range="0801~0827")
    repo.save_report(fresh)

    assert repo.load_report("2026-08-26") is None
    assert repo.load_report("2026-08-27") is not None


def test_weekly_and_monthly_same_date_do_not_interfere(repo):
    """같은 날짜라도 주간/월간은 서로 다른 스냅샷 계열이라 서로를 지우면 안 된다."""
    weekly = make_weekly_report("2026-08-27", week_num=35)
    repo.save_report(weekly)

    monthly = make_monthly_report("2026-08-27", month=8)
    repo.save_report(monthly)

    loaded = repo.load_report("2026-08-27")
    assert loaded is not None
    # 동일 날짜의 두 파일이 서로를 제거하지 않았으므로, 최소 두 종류가 모두 파일로 남아 있어야 한다
    files = list(repo.root.rglob("weekly_change_*.json")) + list(repo.root.rglob("monthly_change_*.json"))
    assert len(files) == 2
