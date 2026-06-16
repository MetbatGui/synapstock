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
