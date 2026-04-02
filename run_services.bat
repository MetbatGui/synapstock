@echo off
chcp 65001 >nul
echo ====================================================
echo   🚀 SynapStock 로컬/윈도우 멀티 프로세스 구동 스크립트
echo ====================================================

echo [1] 의존성(명령어) 동기화 중...
call uv sync

echo [2] 백그라운드 탭에서 FastAPI 웹 서버를 엽니다...
start "SynapStock Web Server" uv run synapstock

echo [3] 백그라운드 탭에서 Telegram 봇 스레드를 엽니다...
start "SynapStock Telegram Bot" uv run synapstock-bot

echo ====================================================
echo 두 서비스가 각각 독립된 터미널 창에서 성공적으로 실행되었습니다!
echo 터미널 창을 끄면 해당 프로세스만 골라서 종료됩니다.
echo ====================================================
