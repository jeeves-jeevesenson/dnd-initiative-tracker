# Update script for D&D Initiative Tracker (Windows)
# This script updates the application to the latest version from GitHub

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$InstallDir = Split-Path -Parent $ScriptDir
$TempDir = "$env:TEMP\dnd-tracker-update-$(Get-Random)"

# Function to cleanup temp files
function Cleanup-TempFiles {
    if (Test-Path $TempDir) {
        Write-Host "Cleaning up temporary files..." -ForegroundColor Yellow
        try {
            Remove-Item -Path $TempDir -Recurse -Force -ErrorAction SilentlyContinue
            Write-Host "✓ Cleanup complete" -ForegroundColor Green
        } catch {
            Write-Host "⚠ Could not fully clean up temporary files at: $TempDir" -ForegroundColor Yellow
        }
    }
}

# Register cleanup
$ErrorActionPreference = "Stop"
trap {
    Cleanup-TempFiles
}

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "D&D Initiative Tracker - Update" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Check if we're in the right directory
if (!(Test-Path "$InstallDir\dnd_initative_tracker.py")) {
    Write-Host "Error: Could not find D&D Initiative Tracker installation" -ForegroundColor Red
    Write-Host "Expected location: $InstallDir" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "Installation directory: $InstallDir" -ForegroundColor White
Write-Host ""

# Check if git is available
try {
    $null = Get-Command git -ErrorAction Stop
} catch {
    Write-Host "Error: Git is not installed or not found in PATH." -ForegroundColor Red
    Write-Host "Please install Git from: https://git-scm.com/download/win" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

# Check if this is a git repository
if (!(Test-Path "$InstallDir\.git")) {
    Write-Host "Error: This installation was not installed via git." -ForegroundColor Red
    Write-Host "Please re-install using the quick-install script to enable updates." -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "Checking for updates..." -ForegroundColor Yellow
Set-Location $InstallDir

# Fetch latest changes
git fetch origin
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: Failed to fetch updates from GitHub" -ForegroundColor Red
    Write-Host "Please check your internet connection and try again." -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    Cleanup-TempFiles
    exit 1
}

# Check if there are updates
$localCommit = git rev-parse HEAD
$remoteCommit = git rev-parse origin/main

if ($localCommit -eq $remoteCommit) {
    Write-Host ""
    Write-Host "✓ You are already up to date!" -ForegroundColor Green
    Read-Host "Press Enter to exit"
    Cleanup-TempFiles
    exit 0
}

Write-Host "✓ Updates available" -ForegroundColor Green
Write-Host ""

# Show what will be updated
Write-Host "Changes to be applied:" -ForegroundColor Cyan
$changes = git log --oneline --decorate HEAD..origin/main
$changes | Select-Object -First 5 | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }
Write-Host ""

# Ask for confirmation
$response = Read-Host "Do you want to update? (y/N)"
if ($response -notmatch '^[Yy]') {
    Write-Host "Update cancelled" -ForegroundColor Yellow
    Cleanup-TempFiles
    exit 0
}

Write-Host ""
Write-Host "Updating application..." -ForegroundColor Yellow

# Pull latest changes
git pull origin main
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: Failed to pull updates" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    Cleanup-TempFiles
    exit 1
}
Write-Host "✓ Application code updated" -ForegroundColor Green

# Update dependencies
$venvPython = "$InstallDir\.venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    Write-Host ""
    Write-Host "Updating dependencies..." -ForegroundColor Yellow
    try {
        & $venvPython -m pip install --upgrade pip --quiet
        & $venvPython -m pip install -r "$InstallDir\requirements.txt" --quiet
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ Dependencies updated" -ForegroundColor Green
        } else {
            Write-Host "⚠ Some dependencies may not have updated correctly" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "⚠ Could not update dependencies: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

# Cleanup temp files
Cleanup-TempFiles

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "✓ Update complete!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "You can now restart the D&D Initiative Tracker to use the updated version." -ForegroundColor White
Write-Host ""
Read-Host "Press Enter to exit"
