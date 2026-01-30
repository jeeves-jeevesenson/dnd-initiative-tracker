# Installation Scripts

This directory contains automated installation and launcher scripts for different platforms.

## Windows 11

### install-windows.bat
Automated installer for Windows 11 (Command Prompt) that:
- Creates installation directory at `%LOCALAPPDATA%\DnDInitiativeTracker`
- Copies all application files
- Sets up a Python virtual environment
- Installs all dependencies
- Creates desktop and Start Menu shortcuts
- Creates a launcher batch file

**Usage:**
```cmd
scripts\install-windows.bat
```

### install-windows.ps1
Alternative automated installer for Windows 11 (PowerShell) with the same features as the batch version. Provides better error handling and colored output.

**Usage:**
```powershell
# May require execution policy change for first-time users:
# Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

.\scripts\install-windows.ps1
```

### launch-windows.bat
Quick launcher script for running the tracker directly from the repository without installation.

**Usage:**
```cmd
scripts\launch-windows.bat
```

### uninstall-windows.bat
Removes the installed application, including all files, shortcuts, and configurations (Command Prompt version).

**Usage:**
```cmd
scripts\uninstall-windows.bat
```

### uninstall-windows.ps1
Removes the installed application, including all files, shortcuts, and configurations (PowerShell version).

**Usage:**
```powershell
.\scripts\uninstall-windows.ps1
```

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
