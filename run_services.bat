@echo off
echo ====================================================
echo   SynapStock Local Multi-Process Launcher
echo ====================================================

echo [1] Syncing dependencies...
call uv sync

echo [2] Starting FastAPI Web Server in a new window...
start "SynapStock Web Server" uv run synapstock

echo [3] Starting Telegram Bot in a new window...
start "SynapStock Telegram Bot" uv run synapstock-bot

echo ====================================================
echo Services have been launched in separate windows!
echo Close the respective window to stop a service.
echo ====================================================
