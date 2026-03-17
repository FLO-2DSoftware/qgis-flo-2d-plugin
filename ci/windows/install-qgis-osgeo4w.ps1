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

Start-Process -FilePath $installer -ArgumentList @(
    "-q",
    "-A",
    "-k",
    "-r", $root,
    "-s", $site,
    "-P", $packages
) -Wait -NoNewWindow

Write-Host "[INFO] Verifying installation..."

$qgisBinCandidates = @(
    (Join-Path $root "bin\qgis-ltr-bin.exe"),
    (Join-Path $root "bin\qgis-bin.exe")
)

$qgisBin = $qgisBinCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
$o4wEnv = Join-Path $root "bin\o4w_env.bat"

Write-Host "[INFO] Contents of $root\bin:"
Get-ChildItem (Join-Path $root "bin") | Select-Object Name

if (-not $qgisBin) {
    throw "QGIS binary not found in expected locations."
}
if (!(Test-Path $o4wEnv)) {
    throw "OSGeo4W environment script not found: $o4wEnv"
}

Write-Host "[INFO] QGIS binary: $qgisBin"
Write-Host "[INFO] o4w_env: $o4wEnv"
Write-Host "[INFO] OSGeo4W QGIS install completed."