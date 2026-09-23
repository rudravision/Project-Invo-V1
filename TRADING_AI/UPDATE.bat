@echo off
REM Fetch only the market data that is missing, then refresh reports.
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

echo === Updating Python packages ===
"%PYEXE%" -m pip install --upgrade -r "%TRADING_AI_ROOT%\requirements.txt"

echo.
echo === Re-probing data sources ===
"%PYEXE%" "%TRADING_AI_ROOT%\scripts\probe_sources.py"

echo.
echo === Downloading missing market data only ===
"%PYEXE%" "%TRADING_AI_ROOT%\scripts\bootstrap_data.py" --root "%TRADING_AI_ROOT%" --yes

echo.
echo === Refreshing reports ===
"%PYEXE%" "%TRADING_AI_ROOT%\scripts\run_pipeline.py" --root "%TRADING_AI_ROOT%"
pause
