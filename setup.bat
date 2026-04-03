@echo off
echo ==========================================
echo   SynapStock Environment Setup Script
echo ==========================================

echo.
echo [1] Checking and syncing Python dependencies...
call uv sync
if %errorlevel% neq 0 (
    echo [ERROR] Failed to sync dependencies. Please make sure 'uv' is installed.
    pause
    exit /b %errorlevel%
)

echo.
echo [2] Installing Playwright browser engine for news scraping...
call uv run playwright install
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install Playwright browser engines.
    pause
    exit /b %errorlevel%
)

echo.
echo [3] Checking for essential configuration files...
if not exist ".env" (
    echo  - [WARNING] '.env' file is missing. Please create it and add your tokens.
) else (
    echo  - [OK] '.env' file detected.
)

if not exist "secrets\client_secret.json" (
    echo  - [WARNING] Google Drive API credentials missing in 'secrets/' directory.
) else (
    echo  - [OK] Google Drive secrets detected.
)

echo.
echo ==========================================
echo Setup Completed Successfully! 
echo You can now run 'run_services.bat' to start the application.
echo ==========================================
pause
