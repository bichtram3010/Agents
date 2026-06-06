@echo off
REM ====================================================
REM   Khoi dong CA backend + frontend trong 2 cua so
REM ====================================================
cd /d %~dp0

REM Build RAG index neu chua co
if not exist backend\data\chroma (
    echo [!] Chua co RAG index. Building...
    call backend\.venv\Scripts\activate.bat 2>nul
    python -m backend.scripts.build_rag_index
)

echo Starting backend in new window...
start "Odoo Backend" cmd /k "%~dp0start-backend.bat"

timeout /t 3 /nobreak >nul

echo Starting frontend in new window...
start "Odoo Frontend" cmd /k "%~dp0start-frontend.bat"

echo.
echo Da khoi dong 2 service:
echo   - Backend : http://localhost:8000
echo   - Frontend: http://localhost:3000
echo.
echo Mo trinh duyet: http://localhost:3000
timeout /t 5 /nobreak >nul
start http://localhost:3000
