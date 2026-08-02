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
#>

$ErrorActionPreference = "Stop"

Write-Host "=== building npmpi.exe ===" -ForegroundColor Cyan

python -m pip install --upgrade pip pyinstaller -q
python -m pip install -e . -q

pyinstaller --onefile --name npmpi --console `
    --paths src `
    src/npmpi/__main__.py

Write-Host "`nBuilt: dist\npmpi.exe" -ForegroundColor Green
Write-Host "Copy it anywhere on PATH, or run install.ps1 to fetch the CI-built release exe from GitHub instead."
