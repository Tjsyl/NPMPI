<#
.SYNOPSIS
  One-time bootstrap installer for npmpi.

.DESCRIPTION
  Checks for python, git, and pipx on PATH, offers to install any that are
  missing via winget (ships with Windows 10/11), then installs npmpi
  straight from GitHub with pipx so the `npmpi` command works from any
  terminal (cmd, PowerShell, Windows Terminal) with no wrapper scripts.

  Safe to re-run any time - e.g. to reinstall after an update.
#>

param(
    [string]$RepoUrl = "https://github.com/USERNAME/npmpi.git"
)

function Test-Command($name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

function Install-Via-Winget($id, $friendlyName) {
    if (-not (Test-Command "winget")) {
        Write-Host "winget isn't available on this machine. Install $friendlyName manually, then re-run this script." -ForegroundColor Yellow
        exit 1
    }
    Write-Host "Installing $friendlyName via winget ..." -ForegroundColor Cyan
    winget install --id $id -e --source winget
}

Write-Host "=== npmpi installer ===" -ForegroundColor Cyan

# 1. Python
if (-not (Test-Command "python")) {
    Write-Host "Python not found on PATH."
    $answer = Read-Host "Install it now via winget? (Y/N)"
    if ($answer -match '^[Yy]') {
        Install-Via-Winget "Python.Python.3.12" "Python 3.12"
        Write-Host "Python installed. You may need to close and reopen this terminal for PATH to update." -ForegroundColor Yellow
        Write-Host "Re-run this script after reopening your terminal." -ForegroundColor Yellow
        exit 0
    } else {
        Write-Host "Install Python from https://python.org (check 'Add to PATH' during install), then re-run this script." -ForegroundColor Yellow
        exit 1
    }
} else {
    Write-Host "Python found: $(python --version)"
}

# 2. git (needed for pip/pipx's git+https:// install)
if (-not (Test-Command "git")) {
    Write-Host "git not found on PATH."
    $answer = Read-Host "Install it now via winget? (Y/N)"
    if ($answer -match '^[Yy]') {
        Install-Via-Winget "Git.Git" "Git"
        Write-Host "git installed. You may need to close and reopen this terminal for PATH to update." -ForegroundColor Yellow
        Write-Host "Re-run this script after reopening your terminal." -ForegroundColor Yellow
        exit 0
    } else {
        Write-Host "Install git from https://git-scm.com, then re-run this script." -ForegroundColor Yellow
        exit 1
    }
} else {
    Write-Host "git found: $(git --version)"
}

# 3. pipx
if (-not (Test-Command "pipx")) {
    Write-Host "pipx not found - installing it now ..." -ForegroundColor Cyan
    python -m pip install --user pipx
    python -m pipx ensurepath
    Write-Host "pipx installed. You may need to close and reopen this terminal for PATH to update." -ForegroundColor Yellow
    Write-Host "Re-run this script after reopening your terminal." -ForegroundColor Yellow
    exit 0
} else {
    Write-Host "pipx found: $(pipx --version)"
}

# 4. npmpi itself
Write-Host "`nInstalling npmpi from $RepoUrl ..." -ForegroundColor Cyan
pipx install "git+$RepoUrl"

Write-Host "`nDone. Open a NEW terminal window and run:  npmpi setup" -ForegroundColor Green
