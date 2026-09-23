@echo off
REM Graceful shutdown: checkpoint the database, stop background tasks.
setlocal
set "TRADING_AI_ROOT=%~dp0"
if "%TRADING_AI_ROOT:~-1%"=="\" set "TRADING_AI_ROOT=%TRADING_AI_ROOT:~0,-1%"
cd /d "%TRADING_AI_ROOT%"
set "PYEXE=%TRADING_AI_ROOT%\.venv\Scripts\python.exe"

echo Stopping TRADING_AI gracefully...
if exist "%PYEXE%" (
    "%PYEXE%" "%TRADING_AI_ROOT%\scripts\shutdown.py" --root "%TRADING_AI_ROOT%"
)

REM Stop a dashboard if one is running on the default port.
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8501" ^| findstr "LISTENING"') do (
    echo Stopping dashboard process %%p
    taskkill /PID %%p /F >nul 2>&1
)
echo Done.
pause
