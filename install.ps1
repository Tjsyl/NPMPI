<#
.SYNOPSIS
  One-time installer for npmpi - downloads the standalone npmpi.exe +
  npmpigui.exe.

.DESCRIPTION
  Downloads the latest npmpi.exe (CLI) and npmpigui.exe (always opens
  straight to the GUI - a separate exe from the CLI one, since a single
  exe can't reliably tell double-click apart from a terminal launch) from
  the GitHub Releases page (built by CI via PyInstaller - no Python/git/
  pipx required on this machine at all) into a local folder, adds that
  folder to your user PATH so `npmpi` works from any terminal (cmd,
  PowerShell, Windows Terminal), and adds a Start Menu shortcut to
  npmpigui.exe for double-click GUI access.

  Safe to re-run any time - it just re-downloads the latest release.

.NOTES
  The exe is built by GitHub Actions, not signed with a code-signing
  certificate. Windows SmartScreen/Defender may flag it as unrecognized
  the first time you run it - that's expected for an unsigned indie
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

$exePaths = @{}
foreach ($exeName in @("npmpi.exe", "npmpigui.exe")) {
    $asset = $release.assets | Where-Object { $_.name -eq $exeName } | Select-Object -First 1
    if (-not $asset) {
        Write-Host "No $exeName found on the latest release ($($release.tag_name))." -ForegroundColor Red
        Write-Host "Either the release workflow hasn't run yet, or build it yourself with build_exe.ps1." -ForegroundColor Yellow
        exit 1
    }

    $exePath = Join-Path $InstallDir $exeName
    Write-Host "Downloading $($release.tag_name) -> $exePath ..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $exePath -Headers @{ "User-Agent" = "npmpi-installer" }
    $exePaths[$exeName] = $exePath
}

try {
    $programsDir = Join-Path ([Environment]::GetFolderPath("StartMenu")) "Programs"
    $shortcutPath = Join-Path $programsDir "npmpi.lnk"
    $wshell = New-Object -ComObject WScript.Shell
    $shortcut = $wshell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $exePaths["npmpigui.exe"]
    $shortcut.WorkingDirectory = $InstallDir
    $shortcut.Description = "Open the npmpi GUI"
    $shortcut.Save()
    Write-Host "Start Menu shortcut created: $shortcutPath" -ForegroundColor Cyan
} catch {
    Write-Host "Could not create a Start Menu shortcut ($_) - you can still run npmpigui.exe directly from $InstallDir." -ForegroundColor Yellow
}

$userPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($userPath -notlike "*$InstallDir*") {
    Write-Host "Adding $InstallDir to your user PATH ..." -ForegroundColor Cyan
    [Environment]::SetEnvironmentVariable("PATH", "$userPath;$InstallDir", "User")
    Write-Host "PATH updated - open a NEW terminal window for this to take effect." -ForegroundColor Yellow
} else {
    Write-Host "$InstallDir is already on PATH."
}

Write-Host "`nDone. In a new terminal, run:  npmpi setup" -ForegroundColor Green
Write-Host "Or use the 'npmpi' shortcut in your Start Menu to open the GUI directly." -ForegroundColor Green
