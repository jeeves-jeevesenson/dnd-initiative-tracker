# Installation Scripts

This directory contains automated installation and launcher scripts for different platforms.

## Quick Install Scripts (Recommended)

### quick-install.sh (Linux/macOS)
One-line installation script that handles everything automatically:
- Clones the repository to `~/.local/share/dnd-initiative-tracker`
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

**Usage:**
```cmd
scripts\uninstall-windows.bat
```

### uninstall-windows.ps1
Removes the installed application, including all files, shortcuts, registry entries, and configurations (PowerShell version).
Removes the application from Windows Add/Remove Programs.
Supports silent mode for automated uninstallation.

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

## Linux

### install-linux.sh
Automated installer for Linux (Debian/Ubuntu-based) that:
- Copies app to `~/.local/share/dnd-initiative-tracker/`
- Installs launcher icons (192x192 and 512x512)
- Registers a desktop menu entry (`.desktop` file)
- Optionally creates and populates a virtual environment

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
