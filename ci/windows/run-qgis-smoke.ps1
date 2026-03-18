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

$bat = @"
@echo off
set QT_QPA_PLATFORM=offscreen
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

cmd.exe /c smoke-runner.bat | Tee-Object -FilePath smoke-test.log
$exitCode = $LASTEXITCODE

Write-Host "[INFO] QGIS process exit code: $exitCode"

if (Test-Path "smoke-test-python.log") {
    Write-Host "========== smoke-test-python.log =========="
    Get-Content "smoke-test-python.log"
    Write-Host "==========================================="
} else {
    Write-Host "[WARN] smoke-test-python.log was not created."
}

if ($exitCode -ne 0) {
    throw "QGIS smoke test failed with exit code $exitCode"
}
