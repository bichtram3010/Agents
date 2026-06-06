@echo off
REM ====================================================
REM   Khởi động Backend FastAPI + Agno multi-agent
REM ====================================================
cd /d %~dp0

echo [1/2] Activating venv...
call backend\.venv\Scripts\activate.bat 2>nul
if errorlevel 1 (
    echo [!] Khong tim thay venv. Tao moi...
    py -m venv backend\.venv
    call backend\.venv\Scripts\activate.bat
    echo [!] Dang cai requirements (mat 1-3 phut lan dau)...
    pip install -r backend\requirements.txt
)

echo.
echo [2/2] Starting uvicorn at http://localhost:8000
echo Press Ctrl+C to stop.
echo.
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
