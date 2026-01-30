@echo off
REM D&D Initiative Tracker - Simple Windows Launcher
REM Quick launch script for running the tracker directly from the repository

setlocal

REM Get script directory
set "SCRIPT_DIR=%~dp0"
set "REPO_DIR=%SCRIPT_DIR%.."

echo Starting D&D Initiative Tracker...
echo.

REM Change to repository directory
cd /d "%REPO_DIR%"

REM Check if virtual environment exists and use pythonw.exe if available to hide console
if exist ".venv\Scripts\pythonw.exe" (
    echo Using virtual environment Python (no console)...
    start "" ".venv\Scripts\pythonw.exe" dnd_initative_tracker.py
) else if exist ".venv\Scripts\python.exe" (
    echo Using virtual environment Python...
    ".venv\Scripts\python.exe" dnd_initative_tracker.py
) else (
    echo Using system Python...
    python dnd_initative_tracker.py
)

endlocal
