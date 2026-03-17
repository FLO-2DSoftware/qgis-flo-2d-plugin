$ErrorActionPreference = "Stop"

$installerUrl = $env:QGIS_INSTALLER_URL
$installDir = $env:QGIS_INSTALL_DIR
$installerName = Split-Path $installerUrl -Leaf
$installerPath = Join-Path $env:RUNNER_TEMP $installerName

Write-Host "[INFO] QGIS_INSTALLER_URL: $installerUrl"
Write-Host "[INFO] QGIS_INSTALL_DIR: $installDir"

if ([string]::IsNullOrWhiteSpace($installerUrl)) {
    throw "QGIS_INSTALLER_URL is empty."
}

Write-Host "[INFO] Downloading QGIS installer..."
Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath

if (!(Test-Path $installerPath)) {
    throw "Installer download failed: $installerPath"
}

Write-Host "[INFO] Installer downloaded to: $installerPath"

Write-Host "[INFO] Installing QGIS silently..."
Start-Process msiexec.exe -ArgumentList @(
    "/i", "`"$installerPath`"",
    "/qn",
    "/norestart",
    "INSTALLDIR=`"$installDir`""
) -Wait -NoNewWindow

Write-Host "[INFO] Verifying installation..."

if (!(Test-Path $installDir)) {
    throw "Install directory was not created: $installDir"
}

$qgisExeCandidates = Get-ChildItem $installDir -Recurse -Filter "qgis-bin.exe" -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty FullName

if (-not $qgisExeCandidates) {
    Write-Host "[WARN] Could not find qgis-bin.exe under $installDir"
    Write-Host "[INFO] Dumping install tree (depth 3)..."
    Get-ChildItem $installDir -Recurse -Depth 3 | Select-Object FullName | Out-String | Write-Host
    throw "QGIS executable not found after installation."
}

$qgisBin = $qgisExeCandidates | Select-Object -First 1
Write-Host "[INFO] Found QGIS executable: $qgisBin"

Write-Host "[INFO] Installation verification passed."