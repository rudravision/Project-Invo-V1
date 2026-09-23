@echo off
setlocal
set "TRADING_AI_ROOT=%~dp0"
if "%TRADING_AI_ROOT:~-1%"=="\" set "TRADING_AI_ROOT=%TRADING_AI_ROOT:~0,-1%"
cd /d "%TRADING_AI_ROOT%"
set "PYEXE=%TRADING_AI_ROOT%\.venv\Scripts\python.exe"
if not exist "%PYEXE%" (
    echo [!] No environment found. Run INSTALL.bat first.
    pause
    exit /b 1
)
"%PYEXE%" "%TRADING_AI_ROOT%\scripts\system_check.py" --root "%TRADING_AI_ROOT%"
echo.
pause
