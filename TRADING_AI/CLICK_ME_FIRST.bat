@echo off
REM ===========================================================================
REM  TRADING_AI - START HERE
REM
REM  This is the only file you need to double-click.
REM  It installs itself the first time, then shows a simple menu.
REM ===========================================================================
title TRADING_AI
setlocal EnableDelayedExpansion

set "TRADING_AI_ROOT=%~dp0"
if "%TRADING_AI_ROOT:~-1%"=="\" set "TRADING_AI_ROOT=%TRADING_AI_ROOT:~0,-1%"
cd /d "%TRADING_AI_ROOT%"

cls
echo.
echo   ==================================================================
echo      TRADING_AI
echo      NSE market research, running from your SSD
echo   ==================================================================
echo.
echo      Folder: %TRADING_AI_ROOT%
echo.

set "PYEXE=%TRADING_AI_ROOT%\.venv\Scripts\python.exe"

REM ---------------------------------------------------------------- install --
if not exist "%PYEXE%" (
    echo   First time here - I need to set things up.
    echo   This takes 2-5 minutes and only happens once.
    echo.

    where python >nul 2>&1
    if errorlevel 1 (
        echo   ------------------------------------------------------------
        echo    PROBLEM: Python is not installed on this computer.
        echo   ------------------------------------------------------------
        echo.
        echo    Python is free. Here is what to do:
        echo.
        echo      1. Go to        https://www.python.org/downloads/
        echo      2. Click the big yellow "Download Python" button
        echo      3. Run the installer
        echo      4. IMPORTANT: on the first screen, TICK the box that says
        echo                    "Add python.exe to PATH"
        echo                    ^(it is at the bottom, easy to miss^)
        echo      5. Click "Install Now", wait for it to finish
        echo      6. Come back and double-click this file again
        echo.
        echo   ------------------------------------------------------------
        echo.
        pause
        exit /b 1
    )

    echo   Found Python. Setting up...
    echo.
    python -m venv "%TRADING_AI_ROOT%\.venv"
    if errorlevel 1 (
        echo.
        echo   Could not create the environment.
        echo   Is the SSD full, or write-protected?
        pause
        exit /b 1
    )

    echo   Downloading the pieces I need ^(this is the slow bit^)...
    echo.
    "%PYEXE%" -m pip install --upgrade pip --quiet
    "%PYEXE%" -m pip install -r "%TRADING_AI_ROOT%\requirements.txt"
    if errorlevel 1 (
        echo.
        echo   Download failed. Check your internet connection and try again.
        pause
        exit /b 1
    )

    "%PYEXE%" -c "import sys; sys.path.insert(0,r'%TRADING_AI_ROOT%'); from pathlib import Path; from app.core.ssd import ensure_project_root; ensure_project_root(Path(r'%TRADING_AI_ROOT%'))"

    if not exist "%TRADING_AI_ROOT%\config\.env" (
        (
            echo # TRADING_AI private settings. Keep this file to yourself.
            echo # Leave blank if you are not using a feature.
            echo TELEGRAM_BOT_TOKEN=
            echo TELEGRAM_CHAT_ID=
            echo UPSTOX_API_KEY=
            echo UPSTOX_API_SECRET=
            echo UPSTOX_ACCESS_TOKEN=
        ) > "%TRADING_AI_ROOT%\config\.env"
    )

    echo.
    echo   ==================================================================
    echo      Setup complete.
    echo   ==================================================================
    echo.
    timeout /t 3 >nul
)

REM ------------------------------------------------------------------- menu --
"%PYEXE%" "%TRADING_AI_ROOT%\scripts\assistant.py"

echo.
pause
