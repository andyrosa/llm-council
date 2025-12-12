@echo off
REM Run conversation analysis with any passed arguments
setlocal
cd /d %~dp0
set "PYTHONPATH=%CD%"
uv run python scripts\analyze_conversations.py --show %*
endlocal
