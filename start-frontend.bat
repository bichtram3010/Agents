@echo off
REM ====================================================
REM   Khởi động Frontend Next.js + CopilotKit
REM ====================================================
cd /d %~dp0\frontend

if not exist node_modules (
    echo [!] node_modules chua co. Cai dat...
    call npm install --legacy-peer-deps
)

REM Bao dam co openai package cho CopilotKit OpenAIAdapter
call npm install openai --legacy-peer-deps 2>nul

if not exist .env.local (
    echo BACKEND_URL=http://localhost:8000 > .env.local
    echo NEXT_PUBLIC_BACKEND_URL=http://localhost:8000 >> .env.local
    echo [!] Da tao .env.local mac dinh
)

echo.
echo Starting Next.js at http://localhost:3000
echo Press Ctrl+C to stop.
echo.
call npm run dev
