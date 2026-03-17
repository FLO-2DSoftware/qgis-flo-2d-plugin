$ErrorActionPreference = "Stop"

$pluginName = $env:PLUGIN_NAME
$qgisRoot   = $env:QGIS_ROOT
$profile    = $env:QGIS_PROFILE
$repoRoot   = (Get-Location).Path

$pluginSrc = Join-Path $repoRoot $pluginName
$qgisProfileRoot = Join-Path $env:APPDATA "QGIS\QGIS3\profiles\$profile"
$pluginParent = Join-Path $qgisProfileRoot "python\plugins"
$pluginDst = Join-Path $pluginParent $pluginName

$qgisBin = Join-Path $qgisRoot "bin\qgis-bin.exe"
$o4wEnv  = Join-Path $qgisRoot "bin\o4w_env.bat"
$qtEnv   = Join-Path $qgisRoot "bin\qt5_env.bat"
$pyEnv   = Join-Path $qgisRoot "bin\py3_env.bat"

if (!(Test-Path $pluginSrc)) {
    throw "Plugin source folder not found: $pluginSrc"
}
if (!(Test-Path $qgisBin)) {
    throw "QGIS binary not found: $qgisBin"
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
call "$qtEnv"
call "$pyEnv"

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

if ($LASTEXITCODE -ne 0) {
    throw "QGIS smoke test failed with exit code $LASTEXITCODE"
}