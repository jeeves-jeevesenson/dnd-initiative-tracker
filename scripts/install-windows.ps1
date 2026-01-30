# D&D Initiative Tracker - Windows 11 Installation Script (PowerShell)
# This script provides an alternative PowerShell-based installer

[CmdletBinding()]
param()

Write-Host "====================================================" -ForegroundColor Cyan
Write-Host "D&D Initiative Tracker - Windows 11 Installation" -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor Cyan
Write-Host ""

# Get script directory and repository directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoDir = Split-Path -Parent $ScriptDir

# Set installation directory
if ($env:INSTALL_DIR) {
    $InstallDir = $env:INSTALL_DIR
} else {
    $InstallDir = Join-Path $env:LOCALAPPDATA "DnDInitiativeTracker"
}

Write-Host "Installation directory: $InstallDir" -ForegroundColor Yellow
Write-Host ""

# Check if Python is installed
try {
    $pythonVersion = & python --version 2>&1
    Write-Host "Found $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "ERROR: Python is not installed or not in PATH." -ForegroundColor Red
    Write-Host "Please install Python 3.9 or higher from https://www.python.org/downloads/" -ForegroundColor Red
    Write-Host "Make sure to check 'Add Python to PATH' during installation." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# Verify Python version is 3.9 or higher
$versionCheck = & python -c "import sys; exit(0 if sys.version_info >= (3, 9) else 1)"
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Python 3.9 or higher is required." -ForegroundColor Red
    Write-Host "Current version: $pythonVersion" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host ""
Write-Host "Creating installation directory..." -ForegroundColor Yellow

# Create installation directory
if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
}

Write-Host "Copying application files..." -ForegroundColor Yellow

# List of files and directories to copy
$itemsToCopy = @(
    "*.py",
    "*.txt",
    "*.md",
    "Monsters",
    "Spells",
    "assets",
    "scripts"
)

# Copy items
foreach ($item in $itemsToCopy) {
    $sourcePath = Join-Path $RepoDir $item
    if (Test-Path $sourcePath) {
        Copy-Item -Path $sourcePath -Destination $InstallDir -Recurse -Force
    }
}

# Copy optional directories if they exist
if (Test-Path (Join-Path $RepoDir "players")) {
    Copy-Item -Path (Join-Path $RepoDir "players") -Destination $InstallDir -Recurse -Force
}
if (Test-Path (Join-Path $RepoDir "presets")) {
    Copy-Item -Path (Join-Path $RepoDir "presets") -Destination $InstallDir -Recurse -Force
}

Write-Host "Creating logs directory..." -ForegroundColor Yellow
$logsDir = Join-Path $InstallDir "logs"
if (-not (Test-Path $logsDir)) {
    New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
}

Write-Host ""
Write-Host "Setting up Python virtual environment..." -ForegroundColor Yellow

$venvDir = Join-Path $InstallDir ".venv"
if (-not (Test-Path $venvDir)) {
    & python -m venv $venvDir
    if ($LASTEXITCODE -ne 0) {
        Write-Host "WARNING: Failed to create virtual environment." -ForegroundColor Yellow
        Write-Host "Continuing without virtual environment..." -ForegroundColor Yellow
    } else {
        Write-Host "Virtual environment created successfully." -ForegroundColor Green
    }
} else {
    Write-Host "Virtual environment already exists." -ForegroundColor Green
}

# Install dependencies if virtual environment was created
$venvPython = Join-Path $venvDir "Scripts\python.exe"
if (Test-Path $venvPython) {
    Write-Host ""
    Write-Host "Installing Python dependencies..." -ForegroundColor Yellow
    $requirementsFile = Join-Path $InstallDir "requirements.txt"
    & $venvPython -m pip install --upgrade pip -q
    & $venvPython -m pip install -r $requirementsFile -q
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Dependencies installed successfully." -ForegroundColor Green
    } else {
        Write-Host "WARNING: Failed to install some dependencies." -ForegroundColor Yellow
        Write-Host "You may need to install them manually." -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Creating launcher script..." -ForegroundColor Yellow

$launcherContent = @"
@echo off
REM D&D Initiative Tracker Launcher
setlocal

set "APP_DIR=%~dp0"
set "LOG_DIR=%APP_DIR%logs"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

cd /d "%APP_DIR%"

if exist "%APP_DIR%.venv\Scripts\python.exe" (
    "%APP_DIR%.venv\Scripts\python.exe" "%APP_DIR%dnd_initative_tracker.py"
) else (
    python "%APP_DIR%dnd_initative_tracker.py"
)

endlocal
"@

$launcherPath = Join-Path $InstallDir "launch-dnd-tracker.bat"
Set-Content -Path $launcherPath -Value $launcherContent

Write-Host ""
Write-Host "Creating desktop and Start Menu shortcuts..." -ForegroundColor Yellow

# Create shortcuts using COM object
$WshShell = New-Object -ComObject WScript.Shell

# Desktop shortcut
$desktopPath = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktopPath "D&D Initiative Tracker.lnk"
$shortcut = $WshShell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $launcherPath
$shortcut.WorkingDirectory = $InstallDir
$shortcut.Description = "D&D Initiative Tracker"
$iconPath = Join-Path $InstallDir "assets\graphic-192.png"
if (Test-Path $iconPath) {
    $shortcut.IconLocation = $iconPath
}
$shortcut.Save()
Write-Host "Desktop shortcut created successfully." -ForegroundColor Green

# Start Menu shortcut
$startMenuPath = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$shortcutPath = Join-Path $startMenuPath "D&D Initiative Tracker.lnk"
$shortcut = $WshShell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $launcherPath
$shortcut.WorkingDirectory = $InstallDir
$shortcut.Description = "D&D Initiative Tracker"
if (Test-Path $iconPath) {
    $shortcut.IconLocation = $iconPath
}
$shortcut.Save()
Write-Host "Start Menu shortcut created successfully." -ForegroundColor Green

Write-Host ""
Write-Host "====================================================" -ForegroundColor Cyan
Write-Host "Installation Complete!" -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Application installed to: $InstallDir" -ForegroundColor Green
Write-Host ""
Write-Host "You can now launch the tracker using:" -ForegroundColor Yellow
Write-Host "  - Desktop shortcut: 'D&D Initiative Tracker'" -ForegroundColor White
Write-Host "  - Start Menu: Search for 'D&D Initiative Tracker'" -ForegroundColor White
Write-Host "  - Command line: $launcherPath" -ForegroundColor White
Write-Host ""
Write-Host "Logs will be stored in: $logsDir" -ForegroundColor Yellow
Write-Host ""
Write-Host "====================================================" -ForegroundColor Cyan
Read-Host "Press Enter to exit"
