<#
.SYNOPSIS
  Build standalone npmpi.exe + npmpigui.exe locally with PyInstaller.

.DESCRIPTION
  Produces dist\npmpi\npmpi.exe (CLI, console subsystem - the folder it
  sits in goes on PATH for terminal use) and dist\npmpigui\npmpigui.exe
  (always opens straight to the GUI, no console at all - what a desktop/
  Start Menu shortcut should point to for double-click use). Both are
  --onedir builds (an exe alongside its dependency files in a folder, not
  a single packed file) so they start almost instantly - PyInstaller's
  --onefile mode has to self-extract Python + all dependencies into a
  fresh temp folder on every single launch, which made npmpigui.exe take
  10+ seconds to open. --onedir runs directly from files already on disk.
  Either way, no Python installation is required on the target machine.
  Must be run ON Windows (PyInstaller doesn't cross-compile).

  Two separate executables rather than one that tries to guess how it was
  launched: PyInstaller's bootloader makes double-click-vs-terminal
  detection from inside a single exe unreliable (tried it, see git
  history / commands/gui.py's docstring for why) - one exe per subsystem
  sidesteps that entirely instead of guessing.

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

Write-Host "=== building npmpi.exe + npmpigui.exe ===" -ForegroundColor Cyan

& $py -m pip install --upgrade pip pyinstaller -q
& $py -m pip install -e . -q

$pyprojectContent = Get-Content -Raw -Path "pyproject.toml"
$version = "0.0.0"
if ($pyprojectContent -match 'version\s*=\s*"([^"]+)"') {
    $version = $Matches[1]
}
Write-Host "Stamping with version $version (from pyproject.toml)" -ForegroundColor DarkGray
& $py scripts/gen_version_info.py $version version_info.txt

$upxDir = $null
if ($NoUpx) {
    Write-Host "Skipping UPX (-NoUpx passed)" -ForegroundColor DarkGray
} else {
    $upxDir = Get-UpxDir
    if ($upxDir) {
        Write-Host "Compressing with UPX from $upxDir" -ForegroundColor DarkGray
    }
}

function Remove-DistFolderWithRetry {
    # PyInstaller only tries once to clear out an old dist\<name> folder
    # before rebuilding it, and gives up hard on a PermissionError. On this
    # machine that folder is under active AV/backup scanning, which
    # sporadically holds a file locked for a second or two right after
    # PyInstaller (or Windows Explorer, if it's open there) touches it -
    # so we clear it out ourselves first, with retries, rather than let
    # PyInstaller's single attempt fail the whole build over a transient lock.
    param([string]$Path)
    if (-not (Test-Path $Path)) { return }
    for ($i = 1; $i -le 6; $i++) {
        try {
            Remove-Item -Recurse -Force $Path -ErrorAction Stop
            return
        } catch {
            if ($i -eq 6) {
                Write-Error "Could not remove $Path after 6 attempts ($_). Close any running npmpi.exe/npmpigui.exe and any Explorer/terminal window sitting inside that folder, then try again."
                exit 1
            }
            Write-Host "  $Path is locked (attempt $i/6, probably antivirus scanning it) - waiting and retrying..." -ForegroundColor DarkGray
            Start-Sleep -Seconds 2
        }
    }
}

function Invoke-PyInstallerBuild {
    param(
        [string]$Name,
        [string]$EntryScript,
        [switch]$Windowed
    )

    Remove-DistFolderWithRetry -Path "dist/$Name"

    $piArgs = @("--onedir", "--noconfirm", "--name", $Name, "--version-file", "version_info.txt",
        "--icon", "src/npmpi/gui/assets/icon.ico",
        "--add-data", "src/npmpi/gui/assets;npmpi/gui/assets",
        "--collect-all", "customtkinter", "--paths", "src", $EntryScript)
    $piArgs += if ($Windowed) { "--windowed" } else { "--console" }
    if ($upxDir) {
        $piArgs = @("--upx-dir", $upxDir) + $piArgs
    }

    Write-Host "`n--- building $Name.exe ---" -ForegroundColor DarkCyan
    & $py -m PyInstaller @piArgs
    if ($LASTEXITCODE -ne 0) {
        # $ErrorActionPreference = "Stop" only catches terminating PowerShell
        # errors, not a nonzero exit code from an external process like this
        # - without this check the script happily carries on to the next
        # build and prints "Built:" at the end even after a real failure
        # (e.g. PyInstaller couldn't replace dist\$Name because the exe from
        # a previous build was still running and had its files locked).
        Write-Error "PyInstaller failed building $Name.exe (exit code $LASTEXITCODE) - see the traceback above. A common cause: $Name.exe from a previous build is still running - close it and try again."
        exit 1
    }
}

Invoke-PyInstallerBuild -Name "npmpi" -EntryScript "src/npmpi/__main__.py"
Invoke-PyInstallerBuild -Name "npmpigui" -EntryScript "src/npmpi/gui_main.py" -Windowed

Write-Host "`nBuilt: dist\npmpi\npmpi.exe (CLI - put dist\npmpi\ on PATH) and dist\npmpigui\npmpigui.exe (always opens the GUI - shortcut this for double-click use)" -ForegroundColor Green
Write-Host "Each is a folder (exe + its dependency files), not a single file - copy the whole folder, not just the exe."
Write-Host "Or run install.ps1 to fetch the CI-built release exes from GitHub instead."
Write-Host "If antivirus flags either build, re-run with .\build_exe.ps1 -NoUpx to rule out UPX compression."
