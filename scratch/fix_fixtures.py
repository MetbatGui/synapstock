import os
import re

TEST_DIR = "tests/integration/statistics"

def fix_fixtures(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # @pytest.fixture 다음에 오는 @pytest.mark.asyncio 제거
    # 그리고 그 밑에 있는 async def test_... 를 def test_... 로 복구
    pattern = r"@pytest\.fixture\s*@pytest\.mark\.asyncio\s*async def (test_[a-zA-Z0-9_]+)\("
    content = re.sub(pattern, r"@pytest.fixture\ndef \1(", content)
    
    # 줄바꿈이 두 개 이상 들어간 경우도 처리
    pattern2 = r"@pytest\.fixture\s*\n\s*@pytest\.mark\.asyncio\s*\n\s*async def (test_[a-zA-Z0-9_]+)\("
    content = re.sub(pattern2, r"@pytest.fixture\ndef \1(", content)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Fixed fixtures in: {filepath}")

if __name__ == "__main__":
    for root, _, files in os.walk(TEST_DIR):
        for file in files:
            if file.startswith("test_") and file.endswith(".py"):
                fix_fixtures(os.path.join(root, file))
