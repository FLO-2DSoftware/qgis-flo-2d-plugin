$ErrorActionPreference = "Stop"

$pluginName = $env:PLUGIN_NAME
$profile = $env:QGIS_PROFILE
$repoRoot = (Get-Location).Path

$pluginSrc = Join-Path $repoRoot $pluginName
$qgisProfileRoot = Join-Path $env:APPDATA "QGIS\QGIS3\profiles\$profile"
$pluginParent = Join-Path $qgisProfileRoot "python\plugins"
$pluginDst = Join-Path $pluginParent $pluginName

if (!(Test-Path $pluginSrc)) {
    throw "Plugin source folder not found: $pluginSrc"
}

if (!(Test-Path "qgis-bin-path.txt")) {
    throw "qgis-bin-path.txt not found. Install step may have failed."
}

$qgisBin = (Get-Content "qgis-bin-path.txt" | Select-Object -First 1).Trim()

if ([string]::IsNullOrWhiteSpace($qgisBin) -or !(Test-Path $qgisBin)) {
    throw "QGIS executable path is invalid: $qgisBin"
}

New-Item -ItemType Directory -Force -Path $pluginParent | Out-Null

if (Test-Path $pluginDst) {
    Remove-Item -Recurse -Force $pluginDst
}

Copy-Item -Recurse -Force $pluginSrc $pluginDst

Write-Host "[INFO] Plugin copied to $pluginDst"
Write-Host "[INFO] Using qgis-bin: $qgisBin"

$codePath = Join-Path $repoRoot "ci\windows\check_plugin_load.py"

# Do not force offscreen on Windows. Let QGIS use the normal desktop backend.
$bat = @"
@echo off
set PLUGIN_NAME=$pluginName
set EXPECTED_QGIS_MAJOR_MINOR=$env:EXPECTED_QGIS_MAJOR_MINOR

echo [INFO] Using qgis-bin: "$qgisBin"
echo [INFO] Using plugin path: "$pluginDst"
echo [INFO] Using code path: "$codePath"
echo [INFO] EXPECTED_QGIS_MAJOR_MINOR=%EXPECTED_QGIS_MAJOR_MINOR%

"$qgisBin" --nologo --noversioncheck --code "$codePath" > smoke-test-python.log 2>&1
exit /b %ERRORLEVEL%
"@

Set-Content -Path smoke-runner.bat -Value $bat -Encoding ASCII

# Run with timeout so hung QGIS versions do not block forever
$process = Start-Process `
    -FilePath "cmd.exe" `
    -ArgumentList "/c smoke-runner.bat" `
    -PassThru `
    -NoNewWindow `
    -RedirectStandardOutput "smoke-test.log" `
    -RedirectStandardError "smoke-test-stderr.log"

$timedOut = $false

try {
    Wait-Process -Id $process.Id -Timeout 240
} catch {
    $timedOut = $true
    Write-Host "[ERROR] QGIS timed out after 240 seconds. Killing process..."
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
}

$process.Refresh()
$exitCode = if ($timedOut) { 124 } else { $process.ExitCode }

Write-Host "[INFO] QGIS process exit code: $exitCode"

if (Test-Path "smoke-test.log") {
    Write-Host "========== smoke-test.log =========="
    Get-Content "smoke-test.log"
    Write-Host "==================================="
} else {
    Write-Host "[WARN] smoke-test.log was not created."
}

if (Test-Path "smoke-test-python.log") {
    Write-Host "====== smoke-test-python.log ======"
    Get-Content "smoke-test-python.log"
    Write-Host "==================================="
} else {
    Write-Host "[WARN] smoke-test-python.log was not created."
}

if (Test-Path "smoke-test-stderr.log") {
    Write-Host "====== smoke-test-stderr.log ======"
    Get-Content "smoke-test-stderr.log"
    Write-Host "==================================="
}

if ($exitCode -ne 0) {
    throw "QGIS smoke test failed with exit code $exitCode"
}
