@echo off
REM ===================================================================
REM  TRADING_AI - one-click program update
REM
REM  Copies the new program files from this downloaded folder into your
REM  existing TRADING_AI installation.
REM
REM  Your data is NOT touched: the database, backups, reports, logs,
REM  settings and Telegram credentials are all left exactly as they are.
REM  Only program code is replaced.
REM ===================================================================
setlocal EnableDelayedExpansion
title TRADING_AI - Update my copy
color 0B

set "SRC=%~dp0TRADING_AI"

echo.
echo  ==============================================
echo    TRADING_AI  -  UPDATE MY COPY
echo  ==============================================
echo.

if not exist "%SRC%\app\gui\server.py" (
  echo  [X] Could not find the new program files.
  echo.
  echo      This file must stay INSIDE the folder you unzipped.
  echo      Expected to find: %SRC%\app
  echo.
  echo      Tip: unzip the download first, then open the unzipped
  echo      folder and double-click this file from in there.
  echo.
  pause
  exit /b 1
)

set "NEWVER=unknown"
if exist "%SRC%\VERSION" set /p NEWVER=<"%SRC%\VERSION"
echo  New version found: %NEWVER%
echo.

REM ---- 1. Find the existing installation --------------------------------
set "DEST="
for %%D in (
  "G:\Trading\TRADING_AI"
  "E:\Trading\TRADING_AI"
  "F:\Trading\TRADING_AI"
  "D:\Trading\TRADING_AI"
  "C:\Trading\TRADING_AI"
  "%USERPROFILE%\Desktop\TRADING_AI"
  "%USERPROFILE%\Documents\TRADING_AI"
) do (
  if not defined DEST if exist "%%~D\app\gui\server.py" set "DEST=%%~D"
)

if defined DEST (
  echo  Found your installation at:
  echo      %DEST%
  echo.
  set /p OK="  Is that the right folder?  (Y/N): "
  if /i not "!OK!"=="Y" set "DEST="
)

if not defined DEST (
  echo.
  echo  Please tell me where TRADING_AI is installed.
  echo  Open the folder in File Explorer, copy the address bar, paste
  echo  it here, then press Enter.
  echo.
  set /p DEST="  Folder path: "
  set "DEST=!DEST:"=!"
)

if not exist "%DEST%\app\gui\server.py" (
  echo.
  echo  [X] That folder does not look like a TRADING_AI installation.
  echo      I expected to find:  %DEST%\app\gui\server.py
  echo.
  echo      Nothing has been changed. Please run this again with the
  echo      correct folder.
  echo.
  pause
  exit /b 1
)

set "OLDVER=unknown"
if exist "%DEST%\VERSION" set /p OLDVER=<"%DEST%\VERSION"

echo.
echo  --------------------------------------------------
echo    From : %SRC%
echo    To   : %DEST%
echo    %OLDVER%   ==^>   %NEWVER%
echo  --------------------------------------------------
echo.
echo  Your database, backups, reports and settings will NOT be touched.
echo.
set /p GO="  Type Y and press Enter to update: "
if /i not "%GO%"=="Y" (
  echo.
  echo  Cancelled. Nothing was changed.
  pause
  exit /b 0
)

REM ---- 2. Copy program files, protecting all user data ------------------
echo.
echo  Copying program files, please wait...
echo.

REM Your data is safe for two reasons:
REM  1. /MIR is deliberately NOT used, so robocopy only adds and replaces -
REM     it never deletes anything already in your installation. Your
REM     database, backups, reports and logs are simply left alone.
REM  2. The download contains no data files to overwrite them with.
REM
REM The excluded names below are matched ANYWHERE in the tree, so they must
REM only ever be throwaway folders. Do NOT add names like "data" here -
REM that would also skip app\data\, which is program code.
robocopy "%SRC%" "%DEST%" /E /NFL /NDL /NJH /NJS /NP ^
  /XD __pycache__ .venv venv .git node_modules ^
  /XF .env *.pyc
set RC=%ERRORLEVEL%

REM robocopy: 0-7 are success codes, 8+ are real failures
if %RC% GEQ 8 (
  echo.
  echo  [X] The copy did not finish cleanly ^(robocopy code %RC%^).
  echo      Your old files are still in place. Close TRADING_AI if it is
  echo      running, then try again.
  echo.
  pause
  exit /b 1
)

REM ---- 3. Confirm ------------------------------------------------------
set "CHECK=unknown"
if exist "%DEST%\VERSION" set /p CHECK=<"%DEST%\VERSION"

echo.
if "%CHECK%"=="%NEWVER%" (
  color 0A
  echo  ==============================================
  echo    DONE.  You are now on version %CHECK%
  echo  ==============================================
  echo.
  echo  Next:
  echo    1. Open TRADING_AI
  echo    2. Check the version shown at the top of the window
  echo    3. Press UPDATE ^& ANALYZE MARKET
  echo.
) else (
  color 0E
  echo  [!] Copy finished, but the version still reads "%CHECK%".
  echo      Close TRADING_AI completely and run this again.
  echo.
)
pause
endlocal
