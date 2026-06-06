@echo off
REM ====================================================
REM   Khoi dong Agno OS Playground - Web UI cho agents
REM ====================================================
cd /d %~dp0

echo [1/2] Activating venv...
call backend\.venv\Scripts\activate.bat 2>nul
if errorlevel 1 (
    echo [!] Khong tim thay venv. Chay start-backend.bat truoc.
    pause
    exit /b 1
)

echo.
echo [2/2] Starting Agno OS at http://localhost:7777
echo Press Ctrl+C to stop.
echo.
uvicorn backend.agno_os:app --reload --host 0.0.0.0 --port 7777
