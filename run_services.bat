@echo off
echo ====================================================
echo   Evenezer Local Multi-Process Launcher
echo ====================================================

echo [1] Syncing dependencies...
call uv sync

echo [2] Starting FastAPI Web Server in a new window...
start "Evenezer Web Server" uv run evenezer

echo [3] Starting Telegram Bot in a new window...
start "Evenezer Telegram Bot" uv run evenezer-bot

echo ====================================================
echo Services have been launched in separate windows!
echo Close the respective window to stop a service.
echo ====================================================
