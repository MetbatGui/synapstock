# 윈도우 파워쉘 셸 명시적 지정 (sh/bash 미인식 오류 해결)
set shell := ["powershell", "-Command"]

# -----------------------------------------------------------------------------
# Evenezer Justfile - Docker & Local Development Command Shortcuts
# -----------------------------------------------------------------------------

# Docker 이미지 빌드
docker-build:
    docker compose build

# Docker 컨테이너 백그라운드 기동
docker-up: docker-build
    docker compose up -d

# Docker 컨테이너 중지 및 리소스 정리
docker-down:
    docker compose down

# Docker 이미지 재빌드 및 재시작 (Clean restart)
docker-restart:
    docker compose down
    docker compose up --build -d

# Docker 실시간 컨테이너 로그 확인
docker-logs:
    docker compose logs -f

# 개발 가상환경 및 불필요한 캐시/데이터 폴더를 제외하고 클린 압축 수행
zip:
    Get-ChildItem -Path . -Exclude ".venv", "data", "scratch", "scripts", "tests", ".coverage", ".git", ".mypy_cache", ".pytest_cache", ".ruff_cache" | Compress-Archive -DestinationPath "..\mindmap_clean.zip" -Force

setup-release:
    git checkout master
    git remote add employers-evenezer https://github.com/guruta71/evenezer.git

# Release to employers-evenezer
# Usage: just release
release:
    git checkout -B release master
    git push -u employers-evenezer release:master
    git checkout master