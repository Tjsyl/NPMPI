<#
.SYNOPSIS
  One-time installer for npmpi - downloads the standalone npmpi.exe.

.DESCRIPTION
  Downloads the latest npmpi.exe from the GitHub Releases page (built by
  CI via PyInstaller - no Python/git/pipx required on this machine at
  all) into a local folder and adds that folder to your user PATH, so
  `npmpi` works from any terminal (cmd, PowerShell, Windows Terminal).

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
    [string]$RepoName = "npmpi",
    [string]$InstallDir = "$env:LOCALAPPDATA\npmpi"
)

$ErrorActionPreference = "Stop"

Write-Host "=== npmpi installer ===" -ForegroundColor Cyan

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

$apiUrl = "https://api.github.com/repos/$RepoOwner/$RepoName/releases/latest"
Write-Host "Checking latest release ($apiUrl) ..."
$release = Invoke-RestMethod -Uri $apiUrl -Headers @{ "User-Agent" = "npmpi-installer" }

$asset = $release.assets | Where-Object { $_.name -eq "npmpi.exe" } | Select-Object -First 1
if (-not $asset) {
    Write-Host "No npmpi.exe found on the latest release ($($release.tag_name))." -ForegroundColor Red
    Write-Host "Either the release workflow hasn't run yet, or build it yourself with build_exe.ps1." -ForegroundColor Yellow
    exit 1
}

$exePath = Join-Path $InstallDir "npmpi.exe"
Write-Host "Downloading $($release.tag_name) -> $exePath ..." -ForegroundColor Cyan
Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $exePath -Headers @{ "User-Agent" = "npmpi-installer" }

$userPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($userPath -notlike "*$InstallDir*") {
    Write-Host "Adding $InstallDir to your user PATH ..." -ForegroundColor Cyan
    [Environment]::SetEnvironmentVariable("PATH", "$userPath;$InstallDir", "User")
    Write-Host "PATH updated - open a NEW terminal window for this to take effect." -ForegroundColor Yellow
} else {
    Write-Host "$InstallDir is already on PATH."
}

Write-Host "`nDone. In a new terminal, run:  npmpi setup" -ForegroundColor Green
