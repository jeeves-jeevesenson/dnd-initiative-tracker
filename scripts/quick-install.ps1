# Quick install script for D&D Initiative Tracker (Windows)
# This script clones the repository, installs dependencies, and sets up the application

$ErrorActionPreference = "Stop"

$InstallDir = "$env:LOCALAPPDATA\DnDInitiativeTracker"
$RepoUrl = "https://github.com/jeeves-jeevesenson/dnd-initiative-tracker.git"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "D&D Initiative Tracker - Quick Install" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Check if Python is installed
$pythonCmd = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $version = & $cmd --version 2>&1
        if ($version -match "Python (\d+)\.(\d+)") {
            $major = [int]$matches[1]
            $minor = [int]$matches[2]
            if ($major -eq 3 -and $minor -ge 9) {
                $pythonCmd = $cmd
                Write-Host "✓ Python $major.$minor found using command: $cmd" -ForegroundColor Green
                break
            }
        }
    } catch {
        continue
    }
}

if ($null -eq $pythonCmd) {
    Write-Host "Error: Python 3.9 or higher is not installed." -ForegroundColor Red
    Write-Host "Please install Python from https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "Make sure to check 'Add Python to PATH' during installation." -ForegroundColor Yellow
    exit 1
}

# Check if git is installed
try {
    $null = Get-Command git -ErrorAction Stop
    Write-Host "✓ Git found" -ForegroundColor Green
} catch {
    Write-Host "Error: Git is not installed." -ForegroundColor Red
    Write-Host "Please install Git from https://git-scm.com/download/win" -ForegroundColor Yellow
    exit 1
}

# Create install directory if it doesn't exist
if (!(Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
}

# Clone or update the repository
if (Test-Path "$InstallDir\.git") {
    Write-Host ""
    Write-Host "Updating existing installation..." -ForegroundColor Yellow
    Set-Location $InstallDir
    git pull
} else {
    Write-Host ""
    Write-Host "Cloning repository to $InstallDir..." -ForegroundColor Yellow
    git clone $RepoUrl $InstallDir
    Set-Location $InstallDir
}

Write-Host ""
Write-Host "Creating virtual environment..." -ForegroundColor Yellow
& $pythonCmd -m venv .venv

Write-Host "Activating virtual environment..." -ForegroundColor Yellow
& "$InstallDir\.venv\Scripts\Activate.ps1"

Write-Host "Installing dependencies..." -ForegroundColor Yellow
& "$InstallDir\.venv\Scripts\python.exe" -m pip install --upgrade pip
& "$InstallDir\.venv\Scripts\python.exe" -m pip install -r requirements.txt

Write-Host ""
Write-Host "Creating launcher script..." -ForegroundColor Yellow
$LauncherBat = "$InstallDir\launch-dnd-tracker.bat"

@"
@echo off
cd /d "$InstallDir"
call .venv\Scripts\activate.bat
python dnd_initative_tracker.py %*
"@ | Out-File -FilePath $LauncherBat -Encoding ASCII

# Create desktop shortcut
Write-Host "Creating desktop shortcut..." -ForegroundColor Yellow
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("$env:USERPROFILE\Desktop\D&D Initiative Tracker.lnk")
$Shortcut.TargetPath = $LauncherBat
$Shortcut.WorkingDirectory = $InstallDir
$Shortcut.Description = "D&D 5e Initiative Tracker"
if (Test-Path "$InstallDir\assets\graphic-192.png") {
    $Shortcut.IconLocation = "$InstallDir\assets\graphic-192.png"
}
$Shortcut.Save()

# Create Start Menu shortcut
Write-Host "Creating Start Menu shortcut..." -ForegroundColor Yellow
$StartMenuDir = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs"
$StartShortcut = $WshShell.CreateShortcut("$StartMenuDir\D&D Initiative Tracker.lnk")
$StartShortcut.TargetPath = $LauncherBat
$StartShortcut.WorkingDirectory = $InstallDir
$StartShortcut.Description = "D&D 5e Initiative Tracker"
if (Test-Path "$InstallDir\assets\graphic-192.png") {
    $StartShortcut.IconLocation = "$InstallDir\assets\graphic-192.png"
}
$StartShortcut.Save()

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "✓ Installation complete!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "To run the D&D Initiative Tracker:" -ForegroundColor White
Write-Host "  1. Use the Desktop shortcut 'D&D Initiative Tracker'" -ForegroundColor White
Write-Host "  2. Search for 'D&D Initiative Tracker' in the Start Menu" -ForegroundColor White
Write-Host "  3. Run: $LauncherBat" -ForegroundColor White
Write-Host ""
