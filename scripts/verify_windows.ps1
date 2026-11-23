# World Brief: collect verification evidence on the Windows host.
# Run from the repository root in PowerShell:
#     powershell -ExecutionPolicy Bypass -File scripts\verify_windows.ps1
# Everything is written to reports\. A step that fails is recorded and the
# script moves on to the next one. This script has not itself been run yet.

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$reports = Join-Path $root "reports"
New-Item -ItemType Directory -Force -Path $reports | Out-Null
$summary = Join-Path $reports "windows-summary.txt"
"World Brief Windows verification, $(Get-Date -Format s)" | Out-File $summary -Encoding utf8

function Record($name, $code) {
    "$name : exit code $code" | Out-File $summary -Append -Encoding utf8
    Write-Host "$name : exit code $code"
}

Set-Location (Join-Path $root "backend")

# 1. Environment: find a Python 3.11+ (PATH, the py launcher, then Miniforge).
$python = $null
foreach ($candidate in @("python", "py", (Join-Path $env:USERPROFILE "miniforge3\python.exe"))) {
    try {
        $version = & $candidate -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -eq 0 -and [version]$version -ge [version]"3.11") { $python = $candidate; break }
    } catch { }
}
if (-not $python) {
    "No Python 3.11 or newer was found (tried python, py, Miniforge)." | Out-File $summary -Append -Encoding utf8
} else {
    "Python: $python ($version)" | Out-File $summary -Append -Encoding utf8
    if (-not (Test-Path ".venv\Scripts\python.exe")) { & $python -m venv .venv }
}
& .\.venv\Scripts\python.exe -m pip install --quiet -e ".[dev,measure]" 2>&1 | Out-File (Join-Path $reports "windows-pip.txt") -Encoding utf8
Record "install" $LASTEXITCODE

# 2. Backend tests on this machine
& .\.venv\Scripts\python.exe -m pytest -v 2>&1 | Out-File (Join-Path $reports "windows-pytest.txt") -Encoding utf8
Record "backend tests" $LASTEXITCODE

# 3. Live feeds
if (-not (Test-Path "config.toml")) { Copy-Item "config.example.toml" "config.toml" }
& .\.venv\Scripts\python.exe -m worldbrief check-feeds --report (Join-Path $reports "feeds.json") 2>&1 | Out-File (Join-Path $reports "feeds.txt") -Encoding utf8
Record "live feeds" $LASTEXITCODE

# 4. LM Studio reachable, then one real run with measurements.
#    Needs lmstudio.chat_model set in backend\config.toml and LM Studio's server started.
& .\.venv\Scripts\python.exe -m worldbrief check-lm 2>&1 | Out-File (Join-Path $reports "lmstudio-models.txt") -Encoding utf8
Record "LM Studio reachable" $LASTEXITCODE
if ($LASTEXITCODE -eq 0) {
    & .\.venv\Scripts\python.exe -m worldbrief run --report (Join-Path $reports "real-run.json") 2>&1 | Out-File (Join-Path $reports "real-run-console.txt") -Encoding utf8
    Record "real run" $LASTEXITCODE
    & .\.venv\Scripts\python.exe -m worldbrief status 2>&1 | Out-File (Join-Path $reports "real-run-status.txt") -Encoding utf8
}

# 5. Android build, complete log kept. Needs Android Studio's JDK or JAVA_HOME (17 or newer).
Set-Location (Join-Path $root "android")
& .\gradlew.bat --no-daemon --stacktrace testDebugUnitTest assembleDebug 2>&1 | Out-File (Join-Path $reports "android-build.log") -Encoding utf8
Record "android build" $LASTEXITCODE

Set-Location $root
Write-Host ""
Write-Host "Done. Send the reports folder back for review."
