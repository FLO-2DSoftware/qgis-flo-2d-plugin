$ErrorActionPreference = "Stop"

$pluginName = $env:PLUGIN_NAME
$qgisRoot   = $env:QGIS_ROOT
$profile    = $env:QGIS_PROFILE
$repoRoot   = (Get-Location).Path

$pluginSrc = Join-Path $repoRoot $pluginName
$qgisProfileRoot = Join-Path $env:APPDATA "QGIS\QGIS3\profiles\$profile"
$pluginParent = Join-Path $qgisProfileRoot "python\plugins"
$pluginDst = Join-Path $pluginParent $pluginName

$qgisBinCandidates = @(
    (Join-Path $qgisRoot "bin\qgis-ltr-bin.exe"),
    (Join-Path $qgisRoot "bin\qgis-bin.exe")
)
$qgisBin = $qgisBinCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

$o4wEnv = Join-Path $qgisRoot "bin\o4w_env.bat"

if (!(Test-Path $pluginSrc)) {
    throw "Plugin source folder not found: $pluginSrc"
}
if (-not $qgisBin) {
    Write-Host "[WARN] Could not find QGIS binary. Contents of $qgisRoot\bin:"
    Get-ChildItem (Join-Path $qgisRoot "bin") | Select-Object Name
    throw "QGIS binary not found in expected locations."
}
if (!(Test-Path $o4wEnv)) {
    throw "OSGeo4W environment script not found: $o4wEnv"
}

New-Item -ItemType Directory -Force -Path $pluginParent | Out-Null

if (Test-Path $pluginDst) {
    Remove-Item -Recurse -Force $pluginDst
}

Copy-Item -Recurse -Force $pluginSrc $pluginDst

Write-Host "[INFO] Plugin copied to $pluginDst"

$codePath = Join-Path $repoRoot "ci\windows\check_plugin_load.py"

$bat = @"
@echo off
call "$o4wEnv"

set QGIS_DEBUG=0
set QT_QPA_PLATFORM=offscreen

echo [INFO] Using qgis-bin: "$qgisBin"
echo [INFO] Using plugin path: "$pluginDst"
echo [INFO] Using code path: "$codePath"

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