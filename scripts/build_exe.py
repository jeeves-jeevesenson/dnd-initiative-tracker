#!/usr/bin/env python3
"""
Build script for creating Windows executable wrapper
This uses PyInstaller to create a standalone .exe with icon
"""
import sys
import subprocess
import shutil
from pathlib import Path


def main():
    """Build the Windows executable"""
    # Get paths
    script_dir = Path(__file__).parent
    repo_dir = script_dir.parent
    launcher_script = repo_dir / "launcher.py"
    icon_file = repo_dir / "assets" / "icon.ico"
    
    # Check requirements
    if not launcher_script.exists():
        print(f"ERROR: Launcher script not found: {launcher_script}")
        return 1
    
    if not icon_file.exists():
        print(f"ERROR: Icon file not found: {icon_file}")
        print("Please run scripts/create_icon.py first")
        return 1
    
    # Check if PyInstaller is installed
    try:
        import PyInstaller
        print(f"Found PyInstaller {PyInstaller.__version__}")
    except ImportError:
        print("PyInstaller not found. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
    
    print("\nBuilding Windows executable...")
    print(f"  Launcher: {launcher_script}")
    print(f"  Icon: {icon_file}")
    print()
    
    # PyInstaller command
    # --noconsole: Don't show console window
    # --onefile: Create a single .exe file
    # --icon: Use our custom icon
    # --name: Name of the output executable
    # --clean: Clean PyInstaller cache
    cmd = [
        "pyinstaller",
        "--noconsole",
        "--onefile",
        f"--icon={icon_file}",
        "--name=DNDInitiativeTracker",
        "--clean",
        str(launcher_script)
    ]
    
    print(f"Running: {' '.join(cmd)}")
    print()
    
    try:
        subprocess.check_call(cmd, cwd=str(repo_dir))
    except subprocess.CalledProcessError as e:
        print(f"\nERROR: Build failed with exit code {e.returncode}")
        return 1
    
    # Check if the .exe was created
    exe_path = repo_dir / "dist" / "DNDInitiativeTracker.exe"
    if exe_path.exists():
        print("\n" + "="*60)
        print("Build successful!")
        print("="*60)
        print(f"\nExecutable created: {exe_path}")
        print(f"Size: {exe_path.stat().st_size / 1024 / 1024:.2f} MB")
        print("\nYou can now distribute this .exe file.")
        print("It includes the launcher and proper icon.")
        return 0
    else:
        print("\nERROR: Executable not found after build")
        return 1


if __name__ == "__main__":
    sys.exit(main())
