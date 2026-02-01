# Installation Scripts

This directory contains automated installation and launcher scripts for different platforms.

## Quick Install Scripts (Recommended)

### quick-install.sh (Linux/macOS)
One-line installation script that handles everything automatically:
- Clones the repository to `~/.local/share/dnd-initiative-tracker`
- On Linux, runs `install-linux.sh` (including the KDE/desktop entry prompt)
- Creates a Python virtual environment
- Installs all dependencies
- Creates a launcher command at `~/.local/bin/dnd-initiative-tracker`

**Usage:**
```bash
# Using curl
curl -sSL https://raw.githubusercontent.com/jeeves-jeevesenson/dnd-initiative-tracker/main/scripts/quick-install.sh | bash

# Using wget
wget -qO- https://raw.githubusercontent.com/jeeves-jeevesenson/dnd-initiative-tracker/main/scripts/quick-install.sh | bash

# Or if repository is already cloned
./scripts/quick-install.sh
```

### quick-install.ps1 (Windows)
One-line installation script for Windows using PowerShell:
- Clones the repository to `%LOCALAPPDATA%\DnDInitiativeTracker`
- Creates a Python virtual environment
- Installs all dependencies
- Creates desktop and Start Menu shortcuts

**Usage:**
```powershell
# One-line install
irm https://raw.githubusercontent.com/jeeves-jeevesenson/dnd-initiative-tracker/main/scripts/quick-install.ps1 | iex

# Or if repository is already cloned
.\scripts\quick-install.ps1
```

## Update Scripts

### update-linux.sh (Linux/macOS)
Automated update script that safely updates the application to the latest version:
- Checks if updates are available from GitHub
- Shows you the changes before applying them
- Pulls latest code from the main branch
- Updates Python dependencies
- **Automatically cleans up temporary files**
- Safe to cancel at any time

**Usage:**
```bash
# From the installation directory
~/.local/share/dnd-initiative-tracker/scripts/update-linux.sh

# Or use the built-in Help → Check for Updates menu in the app
```

**Features:**
- ✓ Shows preview of changes before updating
- ✓ Confirms before making any changes
- ✓ Updates both code and dependencies
- ✓ Cleans up all temporary files automatically
- ✓ Safe cancellation at any point

### update-windows.ps1 (Windows)
Automated update script for Windows:
- Same features as Linux version
- Windows-specific error handling and UI
- Automatically cleans up temporary files in `%TEMP%`
- Works with the quick-install installation

**Usage:**
```powershell
# From the installation directory
cd $env:LOCALAPPDATA\DnDInitiativeTracker
.\scripts\update-windows.ps1

# Or use the built-in Help → Check for Updates menu in the app
```

**Features:**
- ✓ Color-coded output for better visibility
- ✓ Shows preview of changes before updating
- ✓ Confirms before making any changes  
- ✓ Updates both code and dependencies
- ✓ Cleans up all temporary files automatically
- ✓ Detailed error messages with solutions

**Note:** Both update scripts require the application to be installed via git (using quick-install or manual git clone). If you installed from a ZIP download, you'll need to reinstall using the quick-install script to enable updates.

## Windows 11

### install-windows.bat
Automated installer for Windows 11 (Command Prompt) that:
- Creates installation directory at `%LOCALAPPDATA%\DnDInitiativeTracker`
- Copies all application files
- Sets up a Python virtual environment
- Installs all dependencies
- Creates custom Windows icon from PNG assets
- Creates desktop and Start Menu shortcuts with icon
- Uses pythonw.exe to launch without console window
- Registers with Windows Add/Remove Programs
- Creates a launcher batch file

**Usage:**
```cmd
scripts\install-windows.bat
```

**Features:**
- ✓ No console window when launching
- ✓ Custom icon on shortcuts
- ✓ Appears in Add/Remove Programs
- ✓ Professional uninstall workflow

### install-windows.ps1
Alternative automated installer for Windows 11 (PowerShell) with enhanced features:
- Same installation as batch version
- Creates a Windows icon (.ico) from PNG assets
- Optionally builds a standalone .exe with embedded icon (requires PyInstaller)
- Registers the application with Windows Add/Remove Programs
- Provides better error handling and colored output
- Supports silent uninstallation

**Usage:**
```powershell
# May require execution policy change for first-time users:
# Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

.\scripts\install-windows.ps1
```

**Features:**
- ✓ Creates custom Windows icon from PNG assets
- ✓ Builds standalone .exe launcher (no console window)
- ✓ Registers with Windows Add/Remove Programs
- ✓ Shortcuts use custom icon
- ✓ Professional installation experience

### launch-windows.bat
Quick launcher script for running the tracker directly from the repository without installation.
Uses pythonw.exe when available to hide the console window.

**Usage:**
```cmd
scripts\launch-windows.bat
```

### uninstall-windows.bat
Removes the installed application, including all files, shortcuts, registry entries, and configurations (Command Prompt version).
Removes the application from Windows Add/Remove Programs.
If the `INSTALL_DIR` environment variable is not set, the uninstaller will read `InstallLocation` from the registry before falling back to `%LOCALAPPDATA%\DnDInitiativeTracker`.

**Usage:**
```cmd
scripts\uninstall-windows.bat
```

### uninstall-windows.ps1
Removes the installed application, including all files, shortcuts, registry entries, and configurations (PowerShell version).
Removes the application from Windows Add/Remove Programs.
Supports silent mode for automated uninstallation.
If the `INSTALL_DIR` environment variable is not set, the uninstaller will read `InstallLocation` from the registry before falling back to `$env:LOCALAPPDATA\DnDInitiativeTracker`.

**Usage:**
```powershell
# Interactive mode
.\scripts\uninstall-windows.ps1

# Silent mode (no confirmation)
.\scripts\uninstall-windows.ps1 -Silent
```

## Utility Scripts

### create_icon.py
Creates a Windows .ico file from PNG images in the assets directory.
This is automatically run during installation but can be run manually if needed.

**Usage:**
```bash
python scripts/create_icon.py
```

### build_exe.py
Builds a standalone Windows .exe launcher using PyInstaller.
The .exe includes the custom icon and launches without showing a console window.
Requires PyInstaller to be installed.

**Usage:**
```bash
python scripts/build_exe.py
```

**Note:** This is automatically run during PowerShell installation but can be run manually
to create a distributable .exe file.

### check-lan-script.mjs
Extracts inline `<script>` blocks from `assets/web/lan/index.html` and validates their
syntax using Node's `--check` flag. This is also run in CI to prevent syntax errors from
landing on main.

**Usage:**
```bash
node scripts/check-lan-script.mjs
```

### lan-smoke-playwright.py
Launches a local HTTP server, opens `/lan` in Playwright, and fails if a page error
fires or the LAN boot marker does not appear.

**Usage:**
```bash
python scripts/lan-smoke-playwright.py
```

## Linux

### install-linux.sh
Automated installer for Linux (Debian/Ubuntu-based) that:
- Copies app to `~/.local/share/dnd-initiative-tracker/`
- Installs launcher icons (192x192 and 512x512)
- Registers a desktop menu entry (`.desktop` file)
- Optionally creates and populates a virtual environment
- Creates a `~/.local/bin/dnd-initiative-tracker` launcher command

**Usage:**
```bash
./scripts/install-linux.sh

# Or with automatic dependency installation
INSTALL_PIP_DEPS=1 ./scripts/install-linux.sh
```

### uninstall-linux.sh
Removes the installed application from Linux systems.

**Usage:**
```bash
./scripts/uninstall-linux.sh
```

## Notes

- Windows scripts use `.bat` extension and are designed for Command Prompt
- Linux scripts use `.sh` extension and require bash shell
- All scripts are designed to be run from the repository root directory
- Virtual environments are created automatically by the installers
- Manual installation is still possible - see main README.md for instructions
