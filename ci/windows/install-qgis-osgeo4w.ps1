$ErrorActionPreference = "Stop"

$root = $env:QGIS_ROOT
$site = $env:OSGEO4W_SITE
$packages = $env:OSGEO4W_PACKAGES
$installer = Join-Path $env:RUNNER_TEMP "osgeo4w-setup.exe"

Write-Host "[INFO] Downloading OSGeo4W installer..."
Invoke-WebRequest `
  -Uri "https://download.osgeo.org/osgeo4w/v2/osgeo4w-setup.exe" `
  -OutFile $installer

if (!(Test-Path $installer)) {
    throw "OSGeo4W installer download failed: $installer"
}

Write-Host "[INFO] Installing OSGeo4W packages to $root"
Write-Host "[INFO] Site: $site"
Write-Host "[INFO] Packages: $packages"

# Silent install
Start-Process -FilePath $installer -ArgumentList @(
    "-q",
    "-A",
    "-k",
    "-r", $root,
    "-s", $site,
    "-P", $packages
) -Wait -NoNewWindow

Write-Host "[INFO] Verifying installation..."

$qgisBin = Join-Path $root "bin\qgis-bin.exe"
$o4wEnv  = Join-Path $root "bin\o4w_env.bat"
$qtEnv   = Join-Path $root "bin\qt5_env.bat"
$pyEnv   = Join-Path $root "bin\py3_env.bat"

if (!(Test-Path $qgisBin)) {
    throw "QGIS binary not found: $qgisBin"
}
if (!(Test-Path $o4wEnv)) {
    throw "OSGeo4W environment script not found: $o4wEnv"
}
if (!(Test-Path $qtEnv)) {
    throw "Qt environment script not found: $qtEnv"
}
if (!(Test-Path $pyEnv)) {
    throw "Python environment script not found: $pyEnv"
}

Write-Host "[INFO] QGIS binary: $qgisBin"
Write-Host "[INFO] o4w_env: $o4wEnv"
Write-Host "[INFO] qt5_env: $qtEnv"
Write-Host "[INFO] py3_env: $pyEnv"

Write-Host "[INFO] OSGeo4W QGIS install completed."