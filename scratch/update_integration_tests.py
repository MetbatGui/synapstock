import os
import re

TEST_DIR = "tests/integration/statistics"

def convert_to_async(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # 이미 처리된 파일인지 확인 (기본적으로 def test_ 앞에 async가 있는지로 판단)
    if "@pytest.mark.asyncio" in content and "async def test_" in content:
        # 그래도 await가 빠진 부분이 있을 수 있으므로 await만 추가
        pass
    else:
        # 1. import pytest 가 없으면 추가
        if "import pytest" not in content:
            content = "import pytest\n" + content

        # 2. def test_ 를 async def test_ 로 변경하고 @pytest.mark.asyncio 추가
        content = re.sub(r"^(\s*)def test_", r"\1@pytest.mark.asyncio\n\1async def test_", content, flags=re.MULTILINE)

    # 3. 서비스 메소드 호출에 await 추가 (이미 await가 붙은 경우는 제외)
    methods = [
        "get_analyzed_ranking", "get_daily_summary", "get_monthly_ranking", "sync_recent_data",
        "get_ceiling_analysis", "list_available_ceiling_years", "list_available_ceiling_dates",
        "get_capital_increase_data", "get_bonus_issue_data", "get_convertible_bond_data",
        "get_bw_data", "get_new_listing_data", "sync_new_listing_data", "sync_capital_increase_data",
        "get_daily_ranking", "sync_data", "list_available_dates", "list_available_years",
        "_calculate_consecutive_days", "sync_convertible_bond_data", "sync_bw_data"
    ]
    
    # Negative lookbehind to ensure we don't double await
    for method in methods:
        pattern = r"(?<!await )((?:statistics_service|ranking_svc|ceiling_svc|disclosure_svc|ipo_svc|service|self)\." + method + r"\()"
        content = re.sub(pattern, r"await \1", content)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Updated: {filepath}")

if __name__ == "__main__":
    if not os.path.exists(TEST_DIR):
        print(f"Directory not found: {TEST_DIR}")
    else:
        for root, _, files in os.walk(TEST_DIR):
            for file in files:
                if file.startswith("test_") and file.endswith(".py"):
                    convert_to_async(os.path.join(root, file))
