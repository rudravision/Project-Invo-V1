@echo off
REM ===========================================================================
REM  TRADING_AI - portable launcher
REM
REM  Double-click this from the SSD. It works out where it lives, so the SSD
REM  drive letter can change between machines and nothing breaks.
REM ===========================================================================
setlocal EnableDelayedExpansion

REM %~dp0 is this script's own folder -> that IS the project root.
set "TRADING_AI_ROOT=%~dp0"
if "%TRADING_AI_ROOT:~-1%"=="\" set "TRADING_AI_ROOT=%TRADING_AI_ROOT:~0,-1%"
cd /d "%TRADING_AI_ROOT%"

echo ============================================================
echo  TRADING_AI
echo  Root: %TRADING_AI_ROOT%
echo ============================================================
echo.

REM ---- locate the portable Python environment on the SSD -------------------
set "PYEXE=%TRADING_AI_ROOT%\.venv\Scripts\python.exe"
if not exist "%PYEXE%" (
    echo [!] No Python environment found on the SSD.
    echo     Expected: %PYEXE%
    echo.
    echo     Run INSTALL.bat first.
    echo.
    pause
    exit /b 1
)

REM ---- pre-flight checks ---------------------------------------------------
echo Running system check...
echo.
"%PYEXE%" "%TRADING_AI_ROOT%\scripts\system_check.py" --root "%TRADING_AI_ROOT%"
if errorlevel 1 (
    echo.
    echo ============================================================
    echo  SYSTEM CHECK FAILED - not starting.
    echo  Read the CRITICAL FAILURES above and fix them.
    echo ============================================================
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Starting TRADING_AI pipeline
echo ============================================================
echo.
"%PYEXE%" "%TRADING_AI_ROOT%\scripts\run_pipeline.py" --root "%TRADING_AI_ROOT%"
set RC=%errorlevel%

echo.
if %RC% NEQ 0 (
    echo [!] Pipeline exited with code %RC%. See logs\trading_ai.log
) else (
    echo Done. Reports are in: %TRADING_AI_ROOT%\reports
)
echo.
pause
exit /b %RC%
