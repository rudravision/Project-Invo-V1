@echo off
REM ===========================================================================
REM  TRADING_AI
REM
REM  This is the only file you need. Double-click it.
REM  It opens the TRADING_AI window. No commands, no typing.
REM ===========================================================================
setlocal EnableDelayedExpansion

set "TRADING_AI_ROOT=%~dp0"
if "%TRADING_AI_ROOT:~-1%"=="\" set "TRADING_AI_ROOT=%TRADING_AI_ROOT:~0,-1%"
cd /d "%TRADING_AI_ROOT%"

title TRADING_AI

set "PYEXE=%TRADING_AI_ROOT%\.venv\Scripts\pythonw.exe"
set "PYCON=%TRADING_AI_ROOT%\.venv\Scripts\python.exe"

if not exist "%PYCON%" (
    echo.
    echo  ============================================================
    echo   TRADING_AI is not installed yet.
    echo  ============================================================
    echo.
    echo   Please double-click INSTALL.bat first. It only needs to be
    echo   done once, and it takes a few minutes.
    echo.
    pause
    exit /b 1
)

echo.
echo  ============================================================
echo   Starting TRADING_AI...
echo  ============================================================
echo.
echo   The TRADING_AI window will open in a moment.
echo   Keep this small black window open while you work -
echo   closing it shuts TRADING_AI down.
echo.

"%PYCON%" "%TRADING_AI_ROOT%\scripts\launch_gui.py" --root "%TRADING_AI_ROOT%"
set RC=%errorlevel%

if %RC% NEQ 0 (
    echo.
    echo  ------------------------------------------------------------
    echo   TRADING_AI could not start. The details are in:
    echo   %TRADING_AI_ROOT%\logs\trading_ai.log
    echo  ------------------------------------------------------------
    echo.
    pause
)
exit /b %RC%
