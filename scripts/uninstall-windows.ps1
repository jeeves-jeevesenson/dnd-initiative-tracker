# D&D Initiative Tracker - Windows Uninstaller (PowerShell)
# This script uninstalls the D&D Initiative Tracker from Windows

[CmdletBinding()]
param(
    [switch]$Silent
)

Write-Host "====================================================" -ForegroundColor Cyan
Write-Host "D&D Initiative Tracker - Windows Uninstaller" -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor Cyan
Write-Host ""

# Set installation directory
if ($env:INSTALL_DIR) {
    $InstallDir = $env:INSTALL_DIR
} else {
    $uninstallRegPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\DnDInitiativeTracker"
    if (Test-Path $uninstallRegPath) {
        $installLocation = (Get-ItemProperty -Path $uninstallRegPath -Name InstallLocation -ErrorAction SilentlyContinue).InstallLocation
    }
    if ($installLocation) {
        $InstallDir = $installLocation
    } else {
        $InstallDir = Join-Path $env:LOCALAPPDATA "DnDInitiativeTracker"
    }
}

Write-Host "This will remove the D&D Initiative Tracker from your system." -ForegroundColor Yellow
Write-Host "Installation directory: $InstallDir" -ForegroundColor Yellow
Write-Host ""
Write-Host "WARNING: This will delete all files in the installation directory," -ForegroundColor Red
Write-Host "including any custom configurations, saved presets, and logs." -ForegroundColor Red
Write-Host ""

if (-not $Silent) {
    $confirmation = Read-Host "Are you sure you want to continue? (Y/N)"
    if ($confirmation -ne "Y" -and $confirmation -ne "y") {
        Write-Host ""
        Write-Host "Uninstallation cancelled." -ForegroundColor Yellow
        Read-Host "Press Enter to exit"
        exit 0
    }
}

Write-Host ""
Write-Host "Closing running application..." -ForegroundColor Yellow
try {
    Get-Process -Name "DnDInitiativeTracker" -ErrorAction SilentlyContinue | Stop-Process -Force
    Write-Host "✓ Application closed (if it was running)" -ForegroundColor Green
} catch {
    Write-Host "⚠ Could not close running application: $($_.Exception.Message)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Removing shortcuts..." -ForegroundColor Yellow

# Remove desktop shortcut
try {
    $desktopPath = [Environment]::GetFolderPath("Desktop")
    $desktopShortcut = Join-Path $desktopPath "D&D Initiative Tracker.lnk"
    if (Test-Path $desktopShortcut) {
        Remove-Item -Path $desktopShortcut -Force
        Write-Host "✓ Desktop shortcut removed" -ForegroundColor Green
    } else {
        Write-Host "⚠ Desktop shortcut not found" -ForegroundColor Yellow
    }
} catch {
    Write-Host "⚠ Could not remove desktop shortcut: $($_.Exception.Message)" -ForegroundColor Yellow
}

# Remove Start Menu shortcut
try {
    $startMenuPath = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
    $startMenuShortcut = Join-Path $startMenuPath "D&D Initiative Tracker.lnk"
    if (Test-Path $startMenuShortcut) {
        Remove-Item -Path $startMenuShortcut -Force
        Write-Host "✓ Start Menu shortcut removed" -ForegroundColor Green
    } else {
        Write-Host "⚠ Start Menu shortcut not found" -ForegroundColor Yellow
    }
} catch {
    Write-Host "⚠ Could not remove Start Menu shortcut: $($_.Exception.Message)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Removing registry entries..." -ForegroundColor Yellow

# Remove from Add/Remove Programs registry
try {
    $uninstallRegPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\DnDInitiativeTracker"
    if (Test-Path $uninstallRegPath) {
        Remove-Item -Path $uninstallRegPath -Recurse -Force
        Write-Host "✓ Registry entries removed" -ForegroundColor Green
    } else {
        Write-Host "⚠ Registry entries not found" -ForegroundColor Yellow
    }
} catch {
    Write-Host "⚠ Could not remove registry entries: $($_.Exception.Message)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Removing application files..." -ForegroundColor Yellow

if (Test-Path $InstallDir) {
    try {
        $tempScript = Join-Path $env:TEMP ("dnd-tracker-remove-" + [guid]::NewGuid().ToString() + ".ps1")
        @"
param([string]`$TargetDir, [int]`$ParentPid)
if (`$ParentPid) {
    try {
        Wait-Process -Id `$ParentPid -ErrorAction SilentlyContinue
    } catch {
        # Best effort: continue even if the parent process lookup fails.
    }
}
Start-Sleep -Seconds 2
if (Test-Path -LiteralPath `$TargetDir) {
    Remove-Item -LiteralPath `$TargetDir -Recurse -Force
}
try {
    Remove-Item -LiteralPath `$MyInvocation.MyCommand.Path -Force
} catch {
}
"@ | Set-Content -Path $tempScript -Encoding UTF8
        Start-Process -FilePath "powershell.exe" -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$tempScript`" -TargetDir `"$InstallDir`" -ParentPid $PID" -WindowStyle Hidden
        Write-Host "✓ Application files removal scheduled" -ForegroundColor Green
    } catch {
        Write-Host "⚠ Failed to schedule file removal: $($_.Exception.Message)" -ForegroundColor Yellow
        Write-Host "You may need to delete manually: $InstallDir" -ForegroundColor Yellow
    }
} else {
    Write-Host "⚠ Application directory not found. Already uninstalled?" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "====================================================" -ForegroundColor Cyan
Write-Host "Uninstallation Complete!" -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "D&D Initiative Tracker will be removed from your system shortly." -ForegroundColor Green
Write-Host ""

if (-not $Silent) {
    Read-Host "Press Enter to exit"
}
