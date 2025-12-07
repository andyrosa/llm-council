@echo off
REM Kill previous instances by window title (partial match)
powershell -Command "Get-Process | Where-Object { $_.MainWindowTitle -like '*llm-council-backend*' } | Stop-Process -Force" 2>nul
powershell -Command "Get-Process | Where-Object { $_.MainWindowTitle -like '*llm-council-frontend*' } | Stop-Process -Force" 2>nul

REM Wait 3 seconds for TCP ports to be released (RFC 793)
ping -n 4 127.0.0.1 >nul

start "llm-council-backend" cmd /k "cd /d %~dp0 && uv run uvicorn backend.main:app --reload --host 0.0.0.0 --port 8001"
REM Use node directly instead of npm run dev because npm's .cmd wrapper changes the window title,
REM making it impossible to kill by title on restart
start "llm-council-frontend" cmd /k "cd /d %~dp0frontend && node node_modules\vite\bin\vite.js"

REM Wait for Vite to start and detect its port, then launch browser
powershell -Command "$port = $null; while (-not $port) { Start-Sleep -Milliseconds 500; $port = (Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -ge 5173 -and $_.LocalPort -le 5180 } | Select-Object -First 1).LocalPort }; Start-Process \"http://localhost:$port\""
