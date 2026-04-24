from synapstock.domain.statistics.models import ConvertibleBond
from synapstock.infrastructure.adapters.local.statistics_repo import LocalConvertibleBondRepository


def test_save_and_load_convertible_bond_data(tmp_path):
    """전환사채 데이터를 JSON으로 저장하고 다시 로드했을 때 무결성을 검증합니다."""
    # Arrange
    temp_dir = tmp_path / "cb_test"
    repo = LocalConvertibleBondRepository(data_root=str(temp_dir))

    cb_item = ConvertibleBond(
        date="2026-01-01",
        name="테스트종목",
        bond_round="1",
        bond_type="전환사채",
        bond_amount=1000000000,
        fund_operation=1000000000,
        issue_method="사모",
        conversion_price=1000,
        new_shares=1000000,
        shares_ratio=5.0,
        rcp_no="12345"
    )
    items = [cb_item]

    # Act: 저장
    repo.save_data(items)

    # Assert: 파일 생성 확인
    expected_file = temp_dir / "convertible_bond_data.json"
    assert expected_file.exists()

    # Act: 로드
    loaded_items = repo.load_data()

    # Assert: 내용 검증
    assert len(loaded_items) == 1
    loaded_item = loaded_items[0]
    assert loaded_item.name == "테스트종목"
    assert loaded_item.bond_amount == 1000000000
    assert loaded_item.total_fund == 1000000000

def test_load_data_returns_empty_list_if_file_not_exists(tmp_path):
    """파일이 존재하지 않을 때 빈 리스트를 반환하는지 확인합니다."""
    temp_dir = tmp_path / "empty_test"
    repo = LocalConvertibleBondRepository(data_root=str(temp_dir))

    loaded_items = repo.load_data()
    assert loaded_items == []
