<#
.SYNOPSIS
  Build a standalone npmpi.exe locally with PyInstaller.

.DESCRIPTION
  Produces dist\npmpi.exe - a single file with Python + all dependencies
  bundled in, so it runs on a machine with no Python installed at all.
  Must be run ON Windows (PyInstaller doesn't cross-compile).

  This is what the GitHub Actions release workflow (.github/workflows/
  release.yml) runs automatically on every version tag - use this script
  yourself only if you want a local build without waiting on CI, e.g.
  while developing.

  Picks whichever of `python` / `py` actually launches a real interpreter,
  since on many Windows machines `python` resolves to the Microsoft Store's
  App Execution Alias stub instead of a real install (even after
  installing Python from python.org with "Add to PATH" checked) - it just
  prints "Python was not found..." and exits without doing anything.
  Also invokes PyInstaller as `python -m PyInstaller` rather than the bare
  `pyinstaller` command, so it doesn't matter whether pip's Scripts folder
  is on PATH.

  Also compresses the built exe with UPX (downloaded once and cached under
  %LOCALAPPDATA%\npmpi-build-tools) to cut its size down significantly. If
  you ever see the exe get flagged by antivirus and want to rule UPX out,
  re-run with -NoUpx.

.PARAMETER NoUpx
  Skip UPX compression and build a plain (larger) exe.
#>

param(
    [switch]$NoUpx
)

$ErrorActionPreference = "Stop"

function Get-WorkingPythonCommand {
    foreach ($candidate in @("python", "py")) {
        $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        try {
            $out = & $candidate --version 2>&1
            if ($LASTEXITCODE -eq 0 -and $out -match "^Python \d") {
                return $candidate
            }
        } catch {}
    }
    return $null
}

$py = Get-WorkingPythonCommand
if (-not $py) {
    Write-Error @'
No working Python found. python and py either aren't installed or
python is being shadowed by the Windows Store's App Execution Alias
stub (prints "Python was not found..." even with a real Python
installed).

Fix: install Python from https://www.python.org/downloads/ with "Add
python.exe to PATH" checked, then open a NEW PowerShell window. If you
already did that and still see the Store message, disable the alias at
Settings > Apps > Advanced app settings > App execution aliases (turn
off the python.exe / python3.exe entries), then open a new window.
'@
    exit 1
}
Write-Host "Using Python via '$py'" -ForegroundColor DarkGray

function Get-UpxDir {
    $upxVersion = "5.2.0"
    $cacheRoot = Join-Path $env:LOCALAPPDATA "npmpi-build-tools"
    $upxDir = Join-Path $cacheRoot "upx-$upxVersion-win64"
    $upxExe = Join-Path $upxDir "upx.exe"

    if (Test-Path $upxExe) {
        return $upxDir
    }

    Write-Host "Downloading UPX $upxVersion (one-time, cached for future builds)..." -ForegroundColor DarkGray
    try {
        New-Item -ItemType Directory -Force -Path $cacheRoot | Out-Null
        $zipPath = Join-Path $cacheRoot "upx-$upxVersion-win64.zip"
        $url = "https://github.com/upx/upx/releases/download/v$upxVersion/upx-$upxVersion-win64.zip"
        Invoke-WebRequest -Uri $url -OutFile $zipPath -UseBasicParsing
        Expand-Archive -Path $zipPath -DestinationPath $cacheRoot -Force
        Remove-Item $zipPath -Force
    } catch {
        Write-Host "Could not download UPX ($_) - building without compression." -ForegroundColor Yellow
        return $null
    }

    if (Test-Path $upxExe) {
        return $upxDir
    }
    Write-Host "UPX download didn't produce upx.exe where expected - building without compression." -ForegroundColor Yellow
    return $null
}

Write-Host "=== building npmpi.exe ===" -ForegroundColor Cyan

& $py -m pip install --upgrade pip pyinstaller -q
& $py -m pip install -e . -q

$pyinstallerArgs = @("--onefile", "--name", "npmpi", "--console", "--paths", "src", "src/npmpi/__main__.py")

if ($NoUpx) {
    Write-Host "Skipping UPX (-NoUpx passed)" -ForegroundColor DarkGray
} else {
    $upxDir = Get-UpxDir
    if ($upxDir) {
        Write-Host "Compressing with UPX from $upxDir" -ForegroundColor DarkGray
        $pyinstallerArgs = @("--upx-dir", $upxDir) + $pyinstallerArgs
    }
}

& $py -m PyInstaller @pyinstallerArgs

Write-Host "`nBuilt: dist\npmpi.exe" -ForegroundColor Green
Write-Host "Copy it anywhere on PATH, or run install.ps1 to fetch the CI-built release exe from GitHub instead."
Write-Host "If antivirus flags this build, re-run with .\build_exe.ps1 -NoUpx to rule out UPX compression."
