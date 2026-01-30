#!/usr/bin/env python3
"""
Windows launcher wrapper for D&D Initiative Tracker
This script launches the main application without showing a console window
"""
import sys
import os
import subprocess
from pathlib import Path


def main():
    """Launch the D&D Initiative Tracker without console window"""
    # Get the directory where this script is located
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        app_dir = Path(sys.executable).parent
    else:
        # Running as Python script
        app_dir = Path(__file__).parent
    
    # Main tracker script
    tracker_script = app_dir / "dnd_initative_tracker.py"
    
    if not tracker_script.exists():
        # Show error in a GUI messagebox
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "D&D Initiative Tracker Error",
                f"Could not find tracker script:\n{tracker_script}"
            )
        except:
            # Fallback to print
            print(f"ERROR: Could not find tracker script: {tracker_script}")
            input("Press Enter to exit...")
        sys.exit(1)
    
    # Determine which Python to use
    venv_python = app_dir / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        python_exe = str(venv_python)
    else:
        python_exe = sys.executable
    
    # Launch the tracker script without console window
    # Use pythonw.exe if available (Windows-specific, no console)
    if python_exe.endswith("python.exe"):
        pythonw_exe = python_exe.replace("python.exe", "pythonw.exe")
        if Path(pythonw_exe).exists():
            python_exe = pythonw_exe
    
    # Launch the application
    try:
        # Use CREATE_NO_WINDOW flag on Windows to suppress console
        if sys.platform == "win32":
            CREATE_NO_WINDOW = 0x08000000
            subprocess.Popen(
                [python_exe, str(tracker_script)],
                cwd=str(app_dir),
                creationflags=CREATE_NO_WINDOW
            )
        else:
            # On non-Windows, just run normally
            subprocess.Popen(
                [python_exe, str(tracker_script)],
                cwd=str(app_dir)
            )
    except Exception as e:
        # Show error in a GUI messagebox
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "D&D Initiative Tracker Error",
                f"Failed to launch tracker:\n{e}"
            )
        except:
            print(f"ERROR: Failed to launch tracker: {e}")
            input("Press Enter to exit...")
        sys.exit(1)


if __name__ == "__main__":
    main()
