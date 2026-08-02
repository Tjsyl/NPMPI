<#
.SYNOPSIS
  Build the self-extracting npmpi-setup.exe installer with Inno Setup.

.DESCRIPTION
  Builds dist\npmpi.exe first (via build_exe.ps1), then compiles
  npmpi_installer.iss with Inno Setup's command-line compiler (ISCC.exe)
  into installer_output\npmpi-setup.exe.

  Requires Inno Setup 6 installed: https://jrsoftware.org/isinfo.php

.PARAMETER Version
  Version string baked into the installer (shown in Add/Remove Programs
  etc). Pass whatever tag you're building for, e.g. -Version 0.1.6.

.PARAMETER SkipExeBuild
  Skip rebuilding dist\npmpi.exe and use whatever's already there.

.EXAMPLE
  .\build_installer.ps1 -Version 0.1.6
#>

param(
    [string]$Version = "0.0.0-dev",
    [switch]$SkipExeBuild
)

$ErrorActionPreference = "Stop"

if (-not $SkipExeBuild) {
    Write-Host "=== building npmpi.exe first ===" -ForegroundColor Cyan
    & "$PSScriptRoot\build_exe.ps1"
}

$isccCmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if ($isccCmd) {
    $isccPath = $isccCmd.Source
} else {
    $candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
    )
    $isccPath = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $isccPath) {
        Write-Error "ISCC.exe (Inno Setup's compiler) not found. Install Inno Setup 6 from https://jrsoftware.org/isinfo.php, or add it to PATH."
        exit 1
    }
}

Write-Host "=== compiling installer (version $Version) ===" -ForegroundColor Cyan
& $isccPath "/DMyAppVersion=$Version" "$PSScriptRoot\npmpi_installer.iss"
if ($LASTEXITCODE -ne 0) {
    Write-Error "ISCC compile failed (exit $LASTEXITCODE)"
    exit $LASTEXITCODE
}

Write-Host "`nBuilt: installer_output\npmpi-setup.exe" -ForegroundColor Green
