# One-shot repair for a project folder that has no Gradle wrapper jar.
# Paste the whole file into Android Studio's Terminal (PowerShell), or run:
#   powershell -ExecutionPolicy Bypass -File tools\fix_gradle.ps1
#
# What it does:
#   1. finds the JDK Android Studio bundles (no separate Java install needed)
#   2. finds a Gradle that Android Studio already downloaded, else downloads Gradle 8.9 to C:\gradle-8.9
#   3. makes sure local.properties points at your Android SDK
#   4. generates gradlew + gradle-wrapper.jar in ..\android  (so Studio's Build menu works)
#   5. builds the debug APK from the command line

$ErrorActionPreference = "Stop"
$proj = Join-Path (Split-Path -Parent $PSScriptRoot) "android"
if (-not (Test-Path (Join-Path $proj "settings.gradle.kts"))) { $proj = "C:\Invo\android" }
Write-Host "project: $proj"

# 1. JDK bundled with Android Studio
$jbr = @(
    "C:\Program Files\Android\Android Studio\jbr",
    "$env:LOCALAPPDATA\Programs\Android Studio\jbr",
    "$env:ProgramFiles\Android\Android Studio1\jbr"
) | Where-Object { Test-Path (Join-Path $_ "bin\java.exe") } | Select-Object -First 1
if ($jbr) { $env:JAVA_HOME = $jbr; Write-Host "JAVA_HOME: $jbr" }
else { Write-Host "WARNING: no Android Studio jbr found, using java from PATH" }

# 2. Gradle: reuse the one Studio downloaded, else fetch it
$found = Get-ChildItem "$env:USERPROFILE\.gradle\wrapper\dists" -Recurse -Filter "gradle.bat" -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match "gradle-8\." } | Select-Object -First 1
if ($found) {
    $bat = $found.FullName
} else {
    $bat = "C:\gradle-8.9\bin\gradle.bat"
    if (-not (Test-Path $bat)) {
        Write-Host "downloading Gradle 8.9 (~130 MB) ..."
        Invoke-WebRequest "https://services.gradle.org/distributions/gradle-8.9-bin.zip" -OutFile "C:\gradle.zip"
        Expand-Archive "C:\gradle.zip" -DestinationPath "C:\" -Force
    }
}
Write-Host "gradle: $bat"

# 3. local.properties -> SDK path
$lp = Join-Path $proj "local.properties"
if (-not (Test-Path $lp)) {
    $sdk = @(
        "$env:LOCALAPPDATA\Android\Sdk",
        "$env:USERPROFILE\AppData\Local\Android\Sdk",
        "C:\Android\Sdk"
    ) | Where-Object { Test-Path (Join-Path $_ "platform-tools") } | Select-Object -First 1
    if (-not $sdk -and $env:ANDROID_HOME) { $sdk = $env:ANDROID_HOME }
    if (-not $sdk) { throw "Android SDK folder not found. Tell me and I will give you the exact 2-line fix." }
    "sdk.dir=$($sdk -replace '\\','/')" | Set-Content $lp -Encoding ascii
    Write-Host "wrote $lp -> $sdk"
}

# 4 + 5
Set-Location $proj
& $bat wrapper --gradle-version 8.9 --console=plain
if ($LASTEXITCODE -ne 0) { throw "gradle wrapper failed" }
& $bat assembleDebug --console=plain
if ($LASTEXITCODE -ne 0) { throw "assembleDebug failed - copy the red text above and send it" }

$apk = Join-Path $proj "app\build\outputs\apk\debug\app-debug.apk"
Write-Host ""
Write-Host "APK READY: $apk"
Write-Host "Next: install it with"
Write-Host "  & `"$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe`" install -r `"$apk`""
