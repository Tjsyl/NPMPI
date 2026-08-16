<#
.SYNOPSIS
  One-time installer for npmpi - downloads npmpi.exe + npmpigui.exe.

.DESCRIPTION
  Downloads the latest npmpi (CLI) and npmpigui (always opens straight to
  the GUI - a separate exe from the CLI one, since a single exe can't
  reliably tell double-click apart from a terminal launch) from the
  GitHub Releases page (built by CI via PyInstaller - no Python/git/pipx
  required on this machine at all). Each ships as a zip (--onedir builds -
  an exe alongside its dependency files, not a single packed file, so
  they start almost instantly instead of the 10+ seconds --onefile took
  to self-extract on every launch) and gets extracted into its own
  subfolder: <InstallDir>\npmpi\npmpi.exe and
  <InstallDir>\npmpigui\npmpigui.exe.

  <InstallDir>\npmpi (not InstallDir itself) is added to your user PATH
  so `npmpi` works from any terminal (cmd, PowerShell, Windows Terminal),
  and a Start Menu shortcut to npmpigui.exe is added for double-click GUI
  access.

  Safe to re-run any time - it just re-downloads and re-extracts the
  latest release.

.NOTES
  The exes are built by GitHub Actions, not signed with a code-signing
  certificate. Windows SmartScreen/Defender may flag them as unrecognized
  the first time you run them - that's expected for an unsigned indie
  tool, not a sign anything's wrong. Click "More info" -> "Run anyway"
  if you see that prompt, or build it yourself locally with
  build_exe.ps1 if you'd rather not deal with the warning at all.
#>

param(
    [string]$RepoOwner = "tjsyl",
    [string]$RepoName = "NPMPI",
    [string]$InstallDir = "$env:LOCALAPPDATA\npmpi"
)

$ErrorActionPreference = "Stop"

Write-Host "=== npmpi installer ===" -ForegroundColor Cyan

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

$apiUrl = "https://api.github.com/repos/$RepoOwner/$RepoName/releases/latest"
Write-Host "Checking latest release ($apiUrl) ..."
$release = Invoke-RestMethod -Uri $apiUrl -Headers @{ "User-Agent" = "npmpi-installer" }

$appDirs = @{}
foreach ($appName in @("npmpi", "npmpigui")) {
    $zipAssetName = "$appName-windows.zip"
    $asset = $release.assets | Where-Object { $_.name -eq $zipAssetName } | Select-Object -First 1
    if (-not $asset) {
        Write-Host "No $zipAssetName found on the latest release ($($release.tag_name))." -ForegroundColor Red
        Write-Host "Either the release workflow hasn't run yet, or build it yourself with build_exe.ps1." -ForegroundColor Yellow
        exit 1
    }

    $appDir = Join-Path $InstallDir $appName
    $zipPath = Join-Path $InstallDir $zipAssetName
    Write-Host "Downloading $($release.tag_name) -> $zipPath ..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zipPath -Headers @{ "User-Agent" = "npmpi-installer" }

    # Wipe any previous install of this one before extracting, so a re-run
    # can't leave stale files behind from an older build's internals.
    if (Test-Path $appDir) {
        Remove-Item -Recurse -Force $appDir
    }
    Write-Host "Extracting -> $appDir ..." -ForegroundColor Cyan
    Expand-Archive -Path $zipPath -DestinationPath $appDir -Force
    Remove-Item $zipPath -Force

    $appDirs[$appName] = $appDir
}

$guiExePath = Join-Path $appDirs["npmpigui"] "npmpigui.exe"
try {
    $programsDir = Join-Path ([Environment]::GetFolderPath("StartMenu")) "Programs"
    $shortcutPath = Join-Path $programsDir "npmpi.lnk"
    $wshell = New-Object -ComObject WScript.Shell
    $shortcut = $wshell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $guiExePath
    $shortcut.WorkingDirectory = $appDirs["npmpigui"]
    $shortcut.Description = "Open the npmpi GUI"
    $shortcut.Save()
    Write-Host "Start Menu shortcut created: $shortcutPath" -ForegroundColor Cyan
} catch {
    Write-Host "Could not create a Start Menu shortcut ($_) - you can still run npmpigui.exe directly from $guiExePath." -ForegroundColor Yellow
}

$cliDir = $appDirs["npmpi"]
$userPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($userPath -notlike "*$cliDir*") {
    Write-Host "Adding $cliDir to your user PATH ..." -ForegroundColor Cyan
    [Environment]::SetEnvironmentVariable("PATH", "$userPath;$cliDir", "User")
    Write-Host "PATH updated - open a NEW terminal window for this to take effect." -ForegroundColor Yellow
} else {
    Write-Host "$cliDir is already on PATH."
}

Write-Host "`nDone. In a new terminal, run:  npmpi setup" -ForegroundColor Green
Write-Host "Or use the 'npmpi' shortcut in your Start Menu to open the GUI directly." -ForegroundColor Green
