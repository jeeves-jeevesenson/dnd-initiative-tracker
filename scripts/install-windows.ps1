# D&D Initiative Tracker - Windows 11 Installation Script (PowerShell)
# This script provides an alternative PowerShell-based installer

[CmdletBinding()]
param()

# Function to show error popup and wait
function Show-ErrorAndExit {
    param(
        [string]$Title,
        [string]$Message
    )
    
    Write-Host ""
    Write-Host "ERROR: $Title" -ForegroundColor Red
    Write-Host $Message -ForegroundColor Yellow
    Write-Host ""
    
    # Show popup dialog
    try {
        Add-Type -AssemblyName PresentationFramework
        [System.Windows.MessageBox]::Show($Message, "D&D Initiative Tracker - $Title", 'OK', 'Error') | Out-Null
    } catch {
        # Fallback if GUI not available
        Write-Host "Could not display popup dialog." -ForegroundColor Yellow
    }
    
    Read-Host "Press Enter to exit"
    exit 1
}

# Function to show warning popup
function Show-Warning {
    param(
        [string]$Title,
        [string]$Message
    )
    
    Write-Host ""
    Write-Host "WARNING: $Title" -ForegroundColor Yellow
    Write-Host $Message -ForegroundColor Yellow
    Write-Host ""
    
    # Show popup dialog
    try {
        Add-Type -AssemblyName PresentationFramework
        [System.Windows.MessageBox]::Show($Message, "D&D Initiative Tracker - $Title", 'OK', 'Warning') | Out-Null
    } catch {
        # Fallback if GUI not available
        Write-Host "Could not display popup dialog." -ForegroundColor Yellow
    }
}

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
    $message = @"
Python is not installed or not found in PATH.

Please install Python 3.9 or higher from:
    https://www.python.org/downloads/

IMPORTANT: During installation, make sure to check the box:
    ☑ Add Python to PATH

After installing Python, restart PowerShell and run this installer again.
"@
    Show-ErrorAndExit -Title "Python Not Found" -Message $message
}

# Verify Python version is 3.9 or higher
$versionCheck = & python -c "import sys; exit(0 if sys.version_info >= (3, 9) else 1)"
if ($LASTEXITCODE -ne 0) {
    $message = @"
Python 3.9 or higher is required.
Current version: $pythonVersion

Please install Python 3.9 or higher from:
    https://www.python.org/downloads/
"@
    Show-ErrorAndExit -Title "Python Version Too Old" -Message $message
}

Write-Host ""
Write-Host "Creating installation directory..." -ForegroundColor Yellow

# Create installation directory
try {
    if (-not (Test-Path $InstallDir)) {
        New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    }
    Write-Host "✓ Installation directory created" -ForegroundColor Green
} catch {
    Show-ErrorAndExit -Title "Directory Creation Failed" -Message "Failed to create installation directory at: $InstallDir`n`nError: $($_.Exception.Message)"
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
try {
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
    Write-Host "✓ Application files copied" -ForegroundColor Green
} catch {
    Show-ErrorAndExit -Title "File Copy Failed" -Message "Failed to copy application files.`n`nError: $($_.Exception.Message)"
}

Write-Host "Creating logs directory..." -ForegroundColor Yellow
try {
    $logsDir = Join-Path $InstallDir "logs"
    if (-not (Test-Path $logsDir)) {
        New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
    }
    Write-Host "✓ Logs directory created" -ForegroundColor Green
} catch {
    # Non-fatal, just warn
    Write-Host "⚠ Could not create logs directory, continuing..." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Setting up Python virtual environment..." -ForegroundColor Yellow

$venvDir = Join-Path $InstallDir ".venv"
try {
    if (-not (Test-Path $venvDir)) {
        & python -m venv $venvDir
        if ($LASTEXITCODE -ne 0) {
            throw "Virtual environment creation failed with exit code $LASTEXITCODE"
        }
        Write-Host "✓ Virtual environment created successfully" -ForegroundColor Green
    } else {
        Write-Host "✓ Virtual environment already exists" -ForegroundColor Green
    }
} catch {
    Show-Warning -Title "Virtual Environment Failed" -Message "Failed to create virtual environment.`n`nError: $($_.Exception.Message)`n`nContinuing without virtual environment..."
}

# Install dependencies if virtual environment was created
$venvPython = Join-Path $venvDir "Scripts\python.exe"
if (Test-Path $venvPython) {
    Write-Host ""
    Write-Host "Installing Python dependencies..." -ForegroundColor Yellow
    try {
        $requirementsFile = Join-Path $InstallDir "requirements.txt"
        & $venvPython -m pip install --upgrade pip -q
        if ($LASTEXITCODE -ne 0) {
            throw "Pip upgrade failed with exit code $LASTEXITCODE"
        }
        & $venvPython -m pip install -r $requirementsFile -q
        if ($LASTEXITCODE -ne 0) {
            throw "Pip install failed with exit code $LASTEXITCODE"
        }
        Write-Host "✓ Dependencies installed successfully" -ForegroundColor Green
    } catch {
        Show-Warning -Title "Dependency Installation Failed" -Message "Failed to install some dependencies.`n`nError: $($_.Exception.Message)`n`nYou may need to install them manually."
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
try {
    Set-Content -Path $launcherPath -Value $launcherContent
    Write-Host "✓ Launcher script created" -ForegroundColor Green
} catch {
    Show-Warning -Title "Launcher Creation Failed" -Message "Failed to create launcher script.`n`nError: $($_.Exception.Message)"
}

Write-Host ""
Write-Host "Creating desktop and Start Menu shortcuts..." -ForegroundColor Yellow

# Create shortcuts using COM object
try {
    $WshShell = New-Object -ComObject WScript.Shell
    
    # Desktop shortcut
    try {
        $desktopPath = [Environment]::GetFolderPath("Desktop")
        $shortcutPath = Join-Path $desktopPath "D&D Initiative Tracker.lnk"
        $shortcut = $WshShell.CreateShortcut($shortcutPath)
        $shortcut.TargetPath = $launcherPath
        $shortcut.WorkingDirectory = $InstallDir
        $shortcut.Description = "D&D Initiative Tracker"
        # Note: PNG icons not supported for shortcuts - using default icon
        $shortcut.Save()
        Write-Host "✓ Desktop shortcut created successfully" -ForegroundColor Green
    } catch {
        Write-Host "⚠ Could not create desktop shortcut" -ForegroundColor Yellow
    }
    
    # Start Menu shortcut
    try {
        $startMenuPath = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
        $shortcutPath = Join-Path $startMenuPath "D&D Initiative Tracker.lnk"
        $shortcut = $WshShell.CreateShortcut($shortcutPath)
        $shortcut.TargetPath = $launcherPath
        $shortcut.WorkingDirectory = $InstallDir
        $shortcut.Description = "D&D Initiative Tracker"
        # Note: PNG icons not supported for shortcuts - using default icon
        $shortcut.Save()
        Write-Host "✓ Start Menu shortcut created successfully" -ForegroundColor Green
    } catch {
        Write-Host "⚠ Could not create Start Menu shortcut" -ForegroundColor Yellow
    }
} catch {
    Write-Host "⚠ Could not create shortcuts" -ForegroundColor Yellow
}

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
