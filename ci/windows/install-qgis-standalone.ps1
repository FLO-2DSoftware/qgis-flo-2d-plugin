$ErrorActionPreference = "Stop"

$installerUrl = $env:QGIS_INSTALLER_URL
$expectedSeries = $env:EXPECTED_QGIS_MAJOR_MINOR
$installerName = Split-Path $installerUrl -Leaf
$installerPath = Join-Path $env:RUNNER_TEMP $installerName

Write-Host "[INFO] QGIS_INSTALLER_URL: $installerUrl"
Write-Host "[INFO] EXPECTED_QGIS_MAJOR_MINOR: $expectedSeries"

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
    "/norestart"
) -Wait -NoNewWindow

Write-Host "[INFO] Verifying installation..."

$programFilesRoots = @(
    "C:\Program Files",
    "C:\Program Files (x86)"
) | Where-Object { Test-Path $_ }

$qgisDirCandidates = foreach ($root in $programFilesRoots) {
    Get-ChildItem $root -Directory -Filter "QGIS*" -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty FullName
}

$qgisDirCandidates = $qgisDirCandidates | Select-Object -Unique

Write-Host "[INFO] QGIS directory candidates:"
$qgisDirCandidates | ForEach-Object { Write-Host "  $_" }

# Broaden executable discovery for version/layout differences
$qgisExeCandidates = foreach ($dir in $qgisDirCandidates) {
    Get-ChildItem $dir -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -match '^qgis.*-bin\.exe$' -or
            $_.Name -eq 'qgis-bin.exe'
        } |
        Select-Object -ExpandProperty FullName
}

$qgisExeCandidates = $qgisExeCandidates | Select-Object -Unique

if (-not $qgisExeCandidates) {
    Write-Host "[WARN] Could not find any QGIS bin executable."
    foreach ($dir in $qgisDirCandidates) {
        Write-Host "[INFO] Dumping install tree under $dir (depth 4)..."
        Get-ChildItem $dir -Recurse -Depth 4 | Select-Object FullName | Out-String | Write-Host
    }
    throw "QGIS executable not found after installation."
}

Write-Host "[INFO] QGIS executable candidates:"
$qgisExeCandidates | ForEach-Object { Write-Host "  $_" }

# Prefer the expected series, then prefer ltr, then first candidate
$qgisBin = $qgisExeCandidates |
    Where-Object { $_ -match [regex]::Escape($expectedSeries) } |
    Where-Object { $_ -match 'qgis-ltr-bin\.exe$' } |
    Select-Object -First 1

if (-not $qgisBin) {
    $qgisBin = $qgisExeCandidates |
        Where-Object { $_ -match [regex]::Escape($expectedSeries) } |
        Select-Object -First 1
}

if (-not $qgisBin) {
    $qgisBin = $qgisExeCandidates | Select-Object -First 1
    Write-Host "[WARN] No executable matched expected series $expectedSeries. Falling back to first candidate."
}

Write-Host "[INFO] Selected QGIS executable: $qgisBin"

Set-Content -Path qgis-bin-path.txt -Value $qgisBin -Encoding ASCII

Write-Host "[INFO] Installation verification passed."
