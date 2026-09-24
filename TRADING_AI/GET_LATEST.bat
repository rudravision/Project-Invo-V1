@echo off
REM ===================================================================
REM  TRADING_AI - fetch and install the latest version
REM
REM  Tries, in order:
REM    1. git pull          (works with a private repo once you have
REM                          signed in to Git for Windows one time)
REM    2. ZIP download      (only works if the repository is public)
REM    3. clear instructions if neither is possible
REM
REM  Your database, backups, reports, logs and settings are never
REM  touched. Only program files are replaced.
REM ===================================================================
setlocal EnableDelayedExpansion
title TRADING_AI - Get the latest version
color 0B

set "HERE=%~dp0"
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"
set "REPO=https://github.com/rudravision/Project-Invo-V1"
set "BRANCH=arena/01a0cf67-project-invo-v1"

set "OLDVER=unknown"
if exist "%HERE%\VERSION" set /p OLDVER=<"%HERE%\VERSION"

echo.
echo  ==============================================
echo    TRADING_AI  -  GET THE LATEST VERSION
echo  ==============================================
echo.
echo  Installed here : %OLDVER%
echo  Folder         : %HERE%
echo.
echo  Close the TRADING_AI window before continuing.
echo.
pause

REM ---------------------------------------------------------------- 1. git
where git >nul 2>&1
if %ERRORLEVEL%==0 (
  if exist "%HERE%\..\.git" (
    echo  Using git to pull the latest changes...
    echo.
    pushd "%HERE%\.."
    git fetch origin "%BRANCH%"
    if !ERRORLEVEL! NEQ 0 (
      echo.
      echo  [!] git could not reach the repository.
      echo      If it asked for a password, sign in to Git for Windows
      echo      once and run this again.
      popd
      goto :tryzip
    )
    git checkout "%BRANCH%" 2>nul
    git pull --ff-only origin "%BRANCH%"
    if !ERRORLEVEL! NEQ 0 (
      echo.
      echo  [!] The pull did not apply cleanly. Nothing was changed.
      echo      This usually means local edits are in the way.
      popd
      pause
      exit /b 1
    )
    popd
    goto :done
  )
)

:tryzip
REM ------------------------------------------------------------ 2. ZIP
echo.
echo  Trying a direct download instead...
echo.
set "TMPZIP=%TEMP%\trading_ai_update.zip"
set "TMPDIR=%TEMP%\trading_ai_update"
if exist "%TMPDIR%" rd /s /q "%TMPDIR%"

powershell -NoProfile -Command ^
  "$ErrorActionPreference='Stop';" ^
  "try { Invoke-WebRequest -UseBasicParsing -Uri '%REPO%/archive/refs/heads/%BRANCH%.zip' -OutFile '%TMPZIP%'; exit 0 }" ^
  "catch { $c=$_.Exception.Response.StatusCode.value__; Write-Host ('HTTP ' + $c); exit 1 }"

if %ERRORLEVEL% NEQ 0 (
  echo.
  color 0E
  echo  ==============================================
  echo    CANNOT DOWNLOAD AUTOMATICALLY
  echo  ==============================================
  echo.
  echo  The repository is PRIVATE, so a download without a login is
  echo  refused. This is not a fault in the program.
  echo.
  echo  Pick one of these, once, and it never troubles you again:
  echo.
  echo    A. Make the repository public on GitHub.
  echo       Then this button works on its own, with no password
  echo       stored on this computer.
  echo.
  echo    B. Install Git for Windows ^(git-scm.com^) and sign in once.
  echo       This script will then use git and keep working privately.
  echo.
  echo  For now, the manual route still works:
  echo    1. Open %REPO%
  echo    2. Code  ^>  Download ZIP
  echo    3. Unzip, then run UPDATE_MY_COPY.bat
  echo.
  pause
  exit /b 1
)

echo  Unpacking...
powershell -NoProfile -Command ^
  "Expand-Archive -Path '%TMPZIP%' -DestinationPath '%TMPDIR%' -Force"

set "SRC="
for /d %%D in ("%TMPDIR%\*") do (
  if exist "%%~fD\TRADING_AI\app\gui\server.py" set "SRC=%%~fD\TRADING_AI"
)
if not defined SRC (
  echo  [X] The download did not contain the expected files.
  pause
  exit /b 1
)

echo  Copying program files...
robocopy "%SRC%" "%HERE%" /E /NFL /NDL /NJH /NJS /NP ^
  /XD __pycache__ .venv venv .git node_modules ^
  /XF .env *.pyc
if %ERRORLEVEL% GEQ 8 (
  echo  [X] The copy failed. Close TRADING_AI and try again.
  pause
  exit /b 1
)

:done
set "NEWVER=unknown"
if exist "%HERE%\VERSION" set /p NEWVER=<"%HERE%\VERSION"
echo.
if "%NEWVER%"=="%OLDVER%" (
  color 0E
  echo  Finished, but the version is still %NEWVER%.
  echo  You may already have the newest version.
) else (
  color 0A
  echo  ==============================================
  echo    UPDATED:  %OLDVER%  ==^>  %NEWVER%
  echo  ==============================================
  echo.
  echo  Open TRADING_AI and check the version at the top.
)
echo.
pause
endlocal
