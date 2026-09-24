@echo off
REM ===========================================================================
REM  TRADING_AI - INSTALL
REM  Creates a self-contained Python environment ON THE SSD so the internal
REM  disk stays clean and the install travels with the drive.
REM ===========================================================================
setlocal EnableDelayedExpansion

set "TRADING_AI_ROOT=%~dp0"
if "%TRADING_AI_ROOT:~-1%"=="\" set "TRADING_AI_ROOT=%TRADING_AI_ROOT:~0,-1%"
cd /d "%TRADING_AI_ROOT%"

echo ============================================================
echo  TRADING_AI INSTALL
echo  Target: %TRADING_AI_ROOT%
echo ============================================================
echo.

REM ---- find a system Python to bootstrap from ------------------------------
where python >nul 2>&1
if errorlevel 1 (
    echo [!] Python is not on your PATH.
    echo     Install Python 3.10+ from https://www.python.org/downloads/
    echo     and tick "Add python.exe to PATH" during setup.
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo Found Python %PYVER%
echo.

REM ---- create the venv on the SSD ------------------------------------------
if exist "%TRADING_AI_ROOT%\.venv\Scripts\python.exe" (
    echo Virtual environment already exists - reusing it.
) else (
    echo Creating virtual environment on the SSD...
    python -m venv "%TRADING_AI_ROOT%\.venv"
    if errorlevel 1 (
        echo [!] Could not create the virtual environment.
        pause
        exit /b 1
    )
)

set "PYEXE=%TRADING_AI_ROOT%\.venv\Scripts\python.exe"

echo.
echo Installing packages ^(this may take a few minutes^)...
"%PYEXE%" -m pip install --upgrade pip
"%PYEXE%" -m pip install -r "%TRADING_AI_ROOT%\requirements.txt"
if errorlevel 1 (
    echo [!] Package installation failed. Check your internet connection.
    pause
    exit /b 1
)

REM ---- keep pip's cache off the internal disk ------------------------------
setx PIP_CACHE_DIR "%TRADING_AI_ROOT%\.cache\pip" >nul 2>&1

REM ---- create the folder tree ----------------------------------------------
echo.
echo Creating project folders...
"%PYEXE%" -c "import sys; sys.path.insert(0,r'%TRADING_AI_ROOT%'); from app.core.ssd import ensure_project_root; from pathlib import Path; ensure_project_root(Path(r'%TRADING_AI_ROOT%')); print('  folders ready')"

REM ---- credentials template -------------------------------------------------
if not exist "%TRADING_AI_ROOT%\config\.env" (
    echo Creating config\.env template...
    (
        echo # TRADING_AI credentials. KEEP THIS FILE PRIVATE. Never commit it.
        echo # Leave blank to disable the related feature.
        echo TELEGRAM_BOT_TOKEN=
        echo TELEGRAM_CHAT_ID=
        echo # Optional broker API ^(needs your own account^)
        echo UPSTOX_API_KEY=
        echo UPSTOX_API_SECRET=
        echo UPSTOX_ACCESS_TOKEN=
    ) > "%TRADING_AI_ROOT%\config\.env"
)

REM ---- desktop shortcut -----------------------------------------------------
echo.
echo Creating a desktop shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
 "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\TRADING_AI.lnk');" ^
 "$s.TargetPath='%TRADING_AI_ROOT%\TRADING_AI.bat';" ^
 "$s.WorkingDirectory='%TRADING_AI_ROOT%';" ^
 "$s.IconLocation='%SystemRoot%\System32\SHELL32.dll,137';" ^
 "$s.Description='TRADING_AI - market research and decision support';" ^
 "$s.Save()" >nul 2>&1
if exist "%USERPROFILE%\Desktop\TRADING_AI.lnk" (
    echo   Desktop shortcut created.
) else (
    echo   Could not create the shortcut - you can still use TRADING_AI.bat.
)

echo.
echo ============================================================
echo  INSTALL COMPLETE
echo ============================================================
echo.
echo  TO START:  double-click TRADING_AI on your desktop,
echo             or TRADING_AI.bat in this folder.
echo.
echo  Then click the big UPDATE ^& ANALYZE MARKET button.
echo  Everything else happens in the window - no commands needed.
echo.
echo  Advanced / troubleshooting only:
echo    SYSTEM_CHECK.bat                     - verify the installation
echo    python scripts\repair_data.py --diagnose   - inspect data problems
echo    python scripts\sync_data.py --period 5y    - download from the CMD
echo.
pause
