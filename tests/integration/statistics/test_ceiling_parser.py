import pytest

from synapstock.domain.statistics.models import CeilingAnalysisReport
from synapstock.infrastructure.container import container
from synapstock.infrastructure.parsers.excel import CeilingParser


@pytest.mark.asyncio


async def test_parse_real_ceiling_report_from_drive():
    """구글 드라이브의 실데이터를 사용하여 상한가 분석 파서를 검증합니다."""

    # 1. 구글 드라이브에서 파일 가져오기
    drive = container.drive_adapter
    filename = "상한가분석(2026년).xlsx"

    content = await drive.get_file(filename, folder="ceiling")

    if content is None:
        pytest.skip(f"구글 드라이브에서 {filename} 파일을 찾을 수 없어 테스트를 건너뜁니다.")
        return

    # 2. 파서 실행
    report = CeilingParser().parse_ceiling_report(
        content=content,
        title="2026년 상한가 분석 재현 테스트"
    )

    # 3. 결과 검증
    assert isinstance(report, CeilingAnalysisReport)
    assert report.title == "2026년 상한가 분석 재현 테스트"
    assert len(report.items) > 0

    # 데이터 형식 검증
    import re
    date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    assert date_pattern.match(report.start_date)
    assert date_pattern.match(report.end_date)

    # 첫 번째 아이템 상세 검증
    first_item = report.items[0]
    assert first_item.name != ""
    assert isinstance(first_item.closing_prices, list)

    print(f"\n[Test Result] 파싱 성공: {report.title}")
    print(f"기간: {report.start_date} ~ {report.end_date}")
    print(f"총 {len(report.items)}개의 종목 분석됨.")
