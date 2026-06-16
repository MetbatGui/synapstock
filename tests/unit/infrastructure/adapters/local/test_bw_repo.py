from evenezer.domain.statistics.models import BondWithWarrants
from evenezer.infrastructure.adapters.local.statistics_repo import LocalBondWithWarrantsRepository


def test_save_and_load_bw_data(tmp_path):
    """신주인수권부사채 데이터를 JSON으로 저장하고 다시 로드했을 때 무결성을 검증합니다."""
    # Arrange
    temp_dir = tmp_path / "bw_test"
    repo = LocalBondWithWarrantsRepository(data_root=str(temp_dir))

    bw_item = BondWithWarrants(
        date="2026-01-05",
        name="오텍",
        bond_round="13",
        bond_type="신주인수권부사채",
        bond_amount=20000000000,
        fund_acquisition_sec=20000000000,
        issue_method="공모",
        exercise_price=1881,
        warrant_ratio=100.0,
        new_shares=10632642,
        shares_ratio=44.5,
        rcp_no="20260105000068"
    )
    items = [bw_item]

    # Act: 저장
    repo.save_data(items)

    # Assert: 파일 생성 확인 (데이터 파일명은 bw_data.json)
    expected_file = temp_dir / "bw_data.json"
    assert expected_file.exists()

    # Act: 로드
    loaded_items = repo.load_data()

    # Assert: 내용 검증
    assert len(loaded_items) == 1
    loaded_item = loaded_items[0]
    assert loaded_item.name == "오텍"
    assert loaded_item.exercise_price == 1881
    assert loaded_item.total_fund == 20000000000
    assert loaded_item.bond_round == "13"

def test_load_data_returns_empty_list_if_file_not_exists_bw(tmp_path):
    """파일이 존재하지 않을 때 빈 리스트를 반환하는지 확인합니다."""
    temp_dir = tmp_path / "empty_bw_test"
    repo = LocalBondWithWarrantsRepository(data_root=str(temp_dir))

    loaded_items = repo.load_data()
    assert loaded_items == []
