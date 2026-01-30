# Quick install script for D&D Initiative Tracker (Windows)
# This script clones the repository, installs dependencies, and sets up the application

$ErrorActionPreference = "Stop"

$InstallDir = "$env:LOCALAPPDATA\DnDInitiativeTracker"
$RepoUrl = "https://github.com/jeeves-jeevesenson/dnd-initiative-tracker.git"

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
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show($Message, "D&D Initiative Tracker - $Title", 'OK', 'Error')
    
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
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show($Message, "D&D Initiative Tracker - $Title", 'OK', 'Warning')
}

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "D&D Initiative Tracker - Quick Install" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Check execution policy
try {
    $executionPolicy = Get-ExecutionPolicy -Scope CurrentUser
    Write-Host "Current execution policy (CurrentUser): $executionPolicy" -ForegroundColor Cyan
    
    if ($executionPolicy -eq "Restricted" -or $executionPolicy -eq "Undefined") {
        $message = @"
Your PowerShell execution policy is set to '$executionPolicy', which prevents this script from running properly.

To fix this, run PowerShell as Administrator and execute:
    Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

Or run this script with:
    powershell -ExecutionPolicy Bypass -File quick-install.ps1

Would you like to continue anyway? (Some features may not work correctly)
"@
        
        Write-Host ""
        Write-Host "WARNING: Restrictive Execution Policy" -ForegroundColor Yellow
        Write-Host $message -ForegroundColor Yellow
        Write-Host ""
        
        $response = Read-Host "Continue anyway? (y/N)"
        if ($response -notmatch '^[Yy]') {
            Show-ErrorAndExit -Title "Execution Policy" -Message $message
        }
    } else {
        Write-Host "✓ Execution policy is compatible" -ForegroundColor Green
    }
} catch {
    Write-Host "⚠ Could not check execution policy, continuing..." -ForegroundColor Yellow
}

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
    $message = @"
Python 3.9 or higher is not installed or not found in PATH.

Please install Python from: https://www.python.org/downloads/

IMPORTANT: During installation, make sure to check the box that says:
    ☑ Add Python to PATH

After installing Python, restart PowerShell and run this installer again.
"@
    Show-ErrorAndExit -Title "Python Not Found" -Message $message
}

# Check if git is installed
try {
    $null = Get-Command git -ErrorAction Stop
    Write-Host "✓ Git found" -ForegroundColor Green
} catch {
    $message = @"
Git is not installed or not found in PATH.

Please install Git from: https://git-scm.com/download/win

After installing Git, restart PowerShell and run this installer again.
"@
    Show-ErrorAndExit -Title "Git Not Found" -Message $message
}

# Create install directory if it doesn't exist
Write-Host ""
Write-Host "Creating installation directory..." -ForegroundColor Yellow
try {
    if (!(Test-Path $InstallDir)) {
        New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    }
    Write-Host "✓ Installation directory ready: $InstallDir" -ForegroundColor Green
} catch {
    Show-ErrorAndExit -Title "Directory Creation Failed" -Message "Failed to create installation directory at: $InstallDir`n`nError: $($_.Exception.Message)"
}

# Clone or update the repository
try {
    if (Test-Path "$InstallDir\.git") {
        Write-Host ""
        Write-Host "Updating existing installation..." -ForegroundColor Yellow
        Set-Location $InstallDir
        git pull
        if ($LASTEXITCODE -ne 0) {
            throw "Git pull failed with exit code $LASTEXITCODE"
        }
    } else {
        Write-Host ""
        Write-Host "Cloning repository to $InstallDir..." -ForegroundColor Yellow
        git clone $RepoUrl $InstallDir
        if ($LASTEXITCODE -ne 0) {
            throw "Git clone failed with exit code $LASTEXITCODE"
        }
        Set-Location $InstallDir
    }
    Write-Host "✓ Repository ready" -ForegroundColor Green
} catch {
    Show-ErrorAndExit -Title "Git Operation Failed" -Message "Failed to clone or update repository.`n`nError: $($_.Exception.Message)`n`nPlease check your internet connection and try again."
}

Write-Host ""
Write-Host "Creating virtual environment..." -ForegroundColor Yellow
try {
    & $pythonCmd -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        throw "Virtual environment creation failed with exit code $LASTEXITCODE"
    }
    Write-Host "✓ Virtual environment created" -ForegroundColor Green
} catch {
    Show-ErrorAndExit -Title "Virtual Environment Failed" -Message "Failed to create Python virtual environment.`n`nError: $($_.Exception.Message)"
}

Write-Host "Installing dependencies..." -ForegroundColor Yellow
try {
    & "$InstallDir\.venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
    & "$InstallDir\.venv\Scripts\python.exe" -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        throw "Pip install failed with exit code $LASTEXITCODE"
    }
    Write-Host "✓ Dependencies installed" -ForegroundColor Green
} catch {
    Show-ErrorAndExit -Title "Dependency Installation Failed" -Message "Failed to install Python dependencies.`n`nError: $($_.Exception.Message)`n`nPlease check your internet connection and try again."
}

Write-Host ""
Write-Host "Creating launcher script..." -ForegroundColor Yellow
$LauncherBat = "$InstallDir\launch-dnd-tracker.bat"

try {
    @"
@echo off
cd /d "$InstallDir"
call .venv\Scripts\activate.bat
python dnd_initative_tracker.py %*
"@ | Out-File -FilePath $LauncherBat -Encoding ASCII
    Write-Host "✓ Launcher script created" -ForegroundColor Green
} catch {
    Show-Warning -Title "Launcher Creation Failed" -Message "Failed to create launcher script, but installation may still work.`n`nError: $($_.Exception.Message)"
}

# Create desktop shortcut
Write-Host "Creating desktop shortcut..." -ForegroundColor Yellow
try {
    $WshShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WshShell.CreateShortcut("$env:USERPROFILE\Desktop\D&D Initiative Tracker.lnk")
    $Shortcut.TargetPath = $LauncherBat
    $Shortcut.WorkingDirectory = $InstallDir
    $Shortcut.Description = "D&D 5e Initiative Tracker"
    if (Test-Path "$InstallDir\assets\graphic-192.png") {
        $Shortcut.IconLocation = "$InstallDir\assets\graphic-192.png"
    }
    $Shortcut.Save()
    Write-Host "✓ Desktop shortcut created" -ForegroundColor Green
} catch {
    Show-Warning -Title "Shortcut Creation Failed" -Message "Failed to create desktop shortcut, but installation completed successfully.`n`nYou can run the tracker using: $LauncherBat"
}

# Create Start Menu shortcut
Write-Host "Creating Start Menu shortcut..." -ForegroundColor Yellow
try {
    $StartMenuDir = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs"
    $StartShortcut = $WshShell.CreateShortcut("$StartMenuDir\D&D Initiative Tracker.lnk")
    $StartShortcut.TargetPath = $LauncherBat
    $StartShortcut.WorkingDirectory = $InstallDir
    $StartShortcut.Description = "D&D 5e Initiative Tracker"
    if (Test-Path "$InstallDir\assets\graphic-192.png") {
        $StartShortcut.IconLocation = "$InstallDir\assets\graphic-192.png"
    }
    $StartShortcut.Save()
    Write-Host "✓ Start Menu shortcut created" -ForegroundColor Green
} catch {
    Show-Warning -Title "Start Menu Shortcut Failed" -Message "Failed to create Start Menu shortcut, but installation completed successfully."
}

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
Write-Host "Press Enter to exit..." -ForegroundColor Cyan
Read-Host
