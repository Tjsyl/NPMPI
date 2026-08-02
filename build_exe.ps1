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
#>

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

Write-Host "=== building npmpi.exe ===" -ForegroundColor Cyan

& $py -m pip install --upgrade pip pyinstaller -q
& $py -m pip install -e . -q

& $py -m PyInstaller --onefile --name npmpi --console `
    --paths src `
    src/npmpi/__main__.py

Write-Host "`nBuilt: dist\npmpi.exe" -ForegroundColor Green
Write-Host "Copy it anywhere on PATH, or run install.ps1 to fetch the CI-built release exe from GitHub instead."
