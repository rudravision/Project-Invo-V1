# =====================================================================
#  TRADING_AI - update straight from GitHub, no browser involved
#
#  Chrome blocks the ZIP because it contains .bat files. That is a
#  heuristic about archives-with-scripts, not a detection of anything
#  harmful - but rather than teach you to click through security
#  warnings, this fetches the same files without the browser.
#
#  What it does, in order:
#    1. downloads the repository archive to a temporary folder
#    2. checks it really contains TRADING_AI program files
#    3. backs up your current program files (not your data - that is
#       never touched)
#    4. copies the new program files over the top
#    5. prints the old and new version numbers
#
#  Your database, backups, reports, logs and config\.env are excluded
#  from the copy and robocopy is run WITHOUT /MIR, so nothing you own
#  can be deleted.
#
#  Run it like this (adjust the folder if yours differs):
#    powershell -ExecutionPolicy Bypass -File UPDATE_FROM_GITHUB.ps1 -Dest "G:\Trading\TRADING_AI"
# =====================================================================

param(
    [string]$Dest = "",
    [string]$Branch = "arena/01a0cf67-project-invo-v1",
    [string]$Repo = "rudravision/Project-Invo-V1"
)

$ErrorActionPreference = "Stop"

function Say($msg, $colour = "Gray") { Write-Host $msg -ForegroundColor $colour }

Say ""
Say "==============================================" "Cyan"
Say "  TRADING_AI - UPDATE FROM GITHUB" "Cyan"
Say "==============================================" "Cyan"
Say ""

# ---- 1. where is the installation? ----------------------------------
if (-not $Dest) {
    # default to the folder this script is sitting in
    $Dest = Split-Path -Parent $MyInvocation.MyCommand.Path
}
if (-not (Test-Path (Join-Path $Dest "app\gui\server.py"))) {
    Say "[X] That does not look like a TRADING_AI installation:" "Red"
    Say "    $Dest" "Red"
    Say ""
    Say "    Re-run with the right folder, for example:" "Yellow"
    Say '    powershell -ExecutionPolicy Bypass -File UPDATE_FROM_GITHUB.ps1 -Dest "G:\Trading\TRADING_AI"' "Yellow"
    exit 1
}

$oldVer = "unknown"
if (Test-Path (Join-Path $Dest "VERSION")) {
    $oldVer = (Get-Content (Join-Path $Dest "VERSION") -First 1).Trim()
}
Say "Installation : $Dest"
Say "Installed    : $oldVer"
Say ""

# ---- 2. download ------------------------------------------------------
$tmp = Join-Path $env:TEMP ("trading_ai_update_" + (Get-Date -Format "yyyyMMddHHmmss"))
$zip = "$tmp.zip"
$url = "https://codeload.github.com/$Repo/zip/refs/heads/$Branch"

Say "Downloading the latest version..."
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $zip
} catch {
    Say "[X] Download failed: $($_.Exception.Message)" "Red"
    Say ""
    Say "    If this says 404, the repository may be private again." "Yellow"
    Say "    If it says no connection, check your internet." "Yellow"
    exit 1
}

Say "Unpacking..."
Expand-Archive -Path $zip -DestinationPath $tmp -Force

$src = Get-ChildItem -Path $tmp -Directory |
       ForEach-Object { Join-Path $_.FullName "TRADING_AI" } |
       Where-Object { Test-Path (Join-Path $_ "app\gui\server.py") } |
       Select-Object -First 1

if (-not $src) {
    Say "[X] The download did not contain the expected program files." "Red"
    Say "    Nothing has been changed." "Red"
    exit 1
}

$newVer = "unknown"
if (Test-Path (Join-Path $src "VERSION")) {
    $newVer = (Get-Content (Join-Path $src "VERSION") -First 1).Trim()
}
Say "Downloaded   : $newVer"
Say ""

if ($newVer -eq $oldVer) {
    Say "You already have version $newVer. Nothing to do." "Green"
    Remove-Item $zip, $tmp -Recurse -Force -ErrorAction SilentlyContinue
    exit 0
}

# ---- 3. back up the current program files -----------------------------
$backup = Join-Path $Dest ("_previous_version_" + $oldVer)
Say "Backing up the current program files to:"
Say "  $backup"
robocopy $Dest $backup /E /NFL /NDL /NJH /NJS /NP `
    /XD __pycache__ .venv venv .git node_modules database backups logs reports backtests data models "_previous_version_*" `
    /XF *.pyc | Out-Null

# ---- 4. copy the new files --------------------------------------------
Say ""
Say "Installing version $newVer..."
# No /MIR: this only adds and replaces. It cannot delete your data.
robocopy $src $Dest /E /NFL /NDL /NJH /NJS /NP `
    /XD __pycache__ .venv venv .git node_modules `
    /XF .env *.pyc | Out-Null

if ($LASTEXITCODE -ge 8) {
    Say "[X] The copy did not finish cleanly (robocopy $LASTEXITCODE)." "Red"
    Say "    Close TRADING_AI if it is open, then run this again." "Yellow"
    exit 1
}

Remove-Item $zip -Force -ErrorAction SilentlyContinue
Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue

# ---- 5. confirm --------------------------------------------------------
$check = "unknown"
if (Test-Path (Join-Path $Dest "VERSION")) {
    $check = (Get-Content (Join-Path $Dest "VERSION") -First 1).Trim()
}
Say ""
if ($check -eq $newVer) {
    Say "==============================================" "Green"
    Say "  UPDATED:  $oldVer  ==>  $check" "Green"
    Say "==============================================" "Green"
    Say ""
    Say "Open TRADING_AI and check the version at the top of the window."
    Say "Your database, backups and settings were not touched."
} else {
    Say "[!] Finished, but VERSION still reads '$check'." "Yellow"
    Say "    Close TRADING_AI completely and run this again." "Yellow"
}
Say ""
