@echo off
REM Kill previous backend by port.
REM Window title matching doesn't work for the backend because:
REM   1. "start" launches cmd.exe with title "llm-council-backend"
REM   2. cmd.exe runs "uv run uvicorn..." which spawns uv.exe -> uvicorn.exe -> python.exe
REM   3. The original cmd.exe seems to exit even though it's launched with /k, but conhost.exe keeps the window open
REM   4. The taskbar shows the cached title, but Windows APIs (tasklist /V, Get-Process)
REM      report the conhost window title as "N/A", making it invisible to title-based kill, and also to process explorer 'find window' tool
REM   5. The frontend (node) doesn't have this problem - node keeps cmd.exe alive
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8001.*LISTENING"') do taskkill /F /PID %%a 2>nul
REM Kill previous frontend by window title (works because node doesn't replace cmd.exe)
powershell -Command "Get-Process | Where-Object { $_.MainWindowTitle -like '*llm-council-frontend*' } | Stop-Process -Force" 2>nul

REM Wait 3 seconds for TCP ports to be released (RFC 793)
echo Waiting for ports to release...
ping -n 4 127.0.0.1 >nul

REM Start FastAPI backend: uv run executes uvicorn, which starts the ASGI server
REM backend.main:app imports the FastAPI app from backend/main.py
REM --reload enables auto-reloading on code changes, --host 0.0.0.0 listens on all interfaces, --port 8001 sets the port
echo Starting backend on port 8001...
start "llm-council-backend" cmd /k "cd /d %~dp0 && uv run python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8001"
REM Use node directly instead of npm run dev because npm's .cmd wrapper changes the window title,
REM making it impossible to kill by title on restart
echo Starting frontend (Vite)...
start "llm-council-frontend" cmd /k "cd /d %~dp0frontend && node node_modules\vite\bin\vite.js"

REM Wait for Vite to start and detect its port, then launch browser
echo Waiting for Vite to start, then opening browser...
powershell -Command "$port = $null; while (-not $port) { Start-Sleep -Milliseconds 500; $port = (Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -ge 5173 -and $_.LocalPort -le 5180 } | Select-Object -First 1).LocalPort }; Start-Process \"http://localhost:$port\""
echo Done.
