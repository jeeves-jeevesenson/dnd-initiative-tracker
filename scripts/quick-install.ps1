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
    [System.Windows.MessageBox]::Show($Message, "D&D Initiative Tracker - $Title", 'OK', 'Error') | Out-Null
    
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
    [System.Windows.MessageBox]::Show($Message, "D&D Initiative Tracker - $Title", 'OK', 'Warning') | Out-Null
}

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "D&D Initiative Tracker - Quick Install" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Check execution policy
try {
    $executionPolicy = Get-ExecutionPolicy -Scope CurrentUser
    Write-Host "Current execution policy (CurrentUser): $executionPolicy" -ForegroundColor Cyan
    
    if ($executionPolicy -eq "Restricted" -or $executionPolicy -eq "Undefined" -or $executionPolicy -eq "AllSigned") {
        $message = @"
Your PowerShell execution policy is set to '$executionPolicy', which prevents this script from running properly.

To fix this, run PowerShell and execute:
    Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

Or run this script with execution policy bypass (downloaded file):
    powershell -ExecutionPolicy Bypass -File quick-install.ps1

Or for the web install method:
    powershell -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/jeeves-jeevesenson/dnd-initiative-tracker/main/scripts/quick-install.ps1 | iex"

Would you like to continue anyway? (Some features may not work correctly)
"@
        
        Write-Host ""
        Write-Host "WARNING: Restrictive Execution Policy" -ForegroundColor Yellow
        Write-Host $message -ForegroundColor Yellow
        Write-Host ""
        
        $response = Read-Host "Continue anyway? (y/N)"
        if ($response -notmatch '^[Yy]') {
            Write-Host ""
            Write-Host "Installation cancelled by user." -ForegroundColor Yellow
            Write-Host "Please adjust your execution policy and try again." -ForegroundColor Yellow
            Write-Host ""
            Read-Host "Press Enter to exit"
            exit 0
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
    & "$InstallDir\.venv\Scripts\python.exe" -m pip install --upgrade pip 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Pip upgrade failed with exit code $LASTEXITCODE"
    }
    # Use -qq to suppress progress but show errors
    $pipOutput = & "$InstallDir\.venv\Scripts\python.exe" -m pip install -r requirements.txt -qq 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Pip output:" -ForegroundColor Yellow
        Write-Host ($pipOutput | Out-String) -ForegroundColor Gray
        throw "Pip install failed with exit code $LASTEXITCODE"
    }
    Write-Host "✓ Dependencies installed" -ForegroundColor Green
} catch {
    Show-ErrorAndExit -Title "Dependency Installation Failed" -Message "Failed to install Python dependencies.`n`nError: $($_.Exception.Message)`n`nPlease check your internet connection and try again."
}

Write-Host ""
Write-Host "Creating icon file..." -ForegroundColor Yellow
try {
    & "$venvPython" "$InstallDir\scripts\create_icon.py"
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ Icon created successfully" -ForegroundColor Green
    }
} catch {
    Write-Host "⚠ Icon creation failed, continuing without custom icon" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Creating launcher script..." -ForegroundColor Yellow
$LauncherBat = "$InstallDir\launch-dnd-tracker.bat"

try {
    @"
@echo off
REM D&D Initiative Tracker Launcher
setlocal

set "APP_DIR=%~dp0"
set "LOG_DIR=%APP_DIR%logs"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

cd /d "%APP_DIR%"

REM Try to use pythonw.exe to hide console window
if exist "%APP_DIR%.venv\Scripts\pythonw.exe" (
    start "" "%APP_DIR%.venv\Scripts\pythonw.exe" "%APP_DIR%dnd_initative_tracker.py"
) else if exist "%APP_DIR%.venv\Scripts\python.exe" (
    "%APP_DIR%.venv\Scripts\python.exe" "%APP_DIR%dnd_initative_tracker.py"
) else (
    python "%APP_DIR%dnd_initative_tracker.py"
)

endlocal
"@ | Out-File -FilePath $LauncherBat -Encoding ASCII
    Write-Host "✓ Launcher script created" -ForegroundColor Green
} catch {
    Show-Warning -Title "Launcher Creation Failed" -Message "Failed to create launcher script, but installation may still work.`n`nError: $($_.Exception.Message)"
}

# Create desktop shortcut
Write-Host "Creating desktop shortcut..." -ForegroundColor Yellow
$iconPath = "$InstallDir\assets\icon.ico"
try {
    $WshShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WshShell.CreateShortcut("$env:USERPROFILE\Desktop\D&D Initiative Tracker.lnk")
    $Shortcut.TargetPath = $LauncherBat
    $Shortcut.WorkingDirectory = $InstallDir
    $Shortcut.Description = "D&D 5e Initiative Tracker"
    if (Test-Path $iconPath) {
        $Shortcut.IconLocation = $iconPath
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
    if (Test-Path $iconPath) {
        $StartShortcut.IconLocation = $iconPath
    }
    $StartShortcut.Save()
    Write-Host "✓ Start Menu shortcut created" -ForegroundColor Green
} catch {
    Show-Warning -Title "Start Menu Shortcut Failed" -Message "Failed to create Start Menu shortcut, but installation completed successfully."
}

Write-Host ""
Write-Host "Registering with Windows Add/Remove Programs..." -ForegroundColor Yellow
try {
    $uninstallRegPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\DnDInitiativeTracker"
    $uninstallScript = "$InstallDir\scripts\uninstall-windows.ps1"
    
    if (-not (Test-Path $uninstallRegPath)) {
        New-Item -Path $uninstallRegPath -Force | Out-Null
    }
    
    New-ItemProperty -Path $uninstallRegPath -Name "DisplayName" -Value "D&D Initiative Tracker" -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $uninstallRegPath -Name "DisplayVersion" -Value "1.0.0" -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $uninstallRegPath -Name "Publisher" -Value "D&D Initiative Tracker" -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $uninstallRegPath -Name "InstallLocation" -Value $InstallDir -PropertyType String -Force | Out-Null
    $uninstallCommand = "powershell.exe -ExecutionPolicy Bypass -Command `"`$env:INSTALL_DIR='$InstallDir'; & `"$uninstallScript`"`""
    $quietUninstallCommand = "powershell.exe -ExecutionPolicy Bypass -Command `"`$env:INSTALL_DIR='$InstallDir'; & `"$uninstallScript`" -Silent`""
    New-ItemProperty -Path $uninstallRegPath -Name "UninstallString" -Value $uninstallCommand -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $uninstallRegPath -Name "QuietUninstallString" -Value $quietUninstallCommand -PropertyType String -Force | Out-Null
    
    if (Test-Path $iconPath) {
        New-ItemProperty -Path $uninstallRegPath -Name "DisplayIcon" -Value $iconPath -PropertyType String -Force | Out-Null
    }
    
    New-ItemProperty -Path $uninstallRegPath -Name "NoModify" -Value 1 -PropertyType DWord -Force | Out-Null
    New-ItemProperty -Path $uninstallRegPath -Name "NoRepair" -Value 1 -PropertyType DWord -Force | Out-Null
    
    Write-Host "✓ Registered with Add/Remove Programs" -ForegroundColor Green
} catch {
    Write-Host "⚠ Could not register with Add/Remove Programs: $($_.Exception.Message)" -ForegroundColor Yellow
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
