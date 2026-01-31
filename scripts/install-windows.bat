@echo off
REM D&D Initiative Tracker - Windows 11 Installation Script
REM This script installs the D&D Initiative Tracker for Windows 11

setlocal EnableDelayedExpansion

echo ====================================================
echo D&D Initiative Tracker - Windows 11 Installation
echo ====================================================
echo.

REM Get script directory and repository directory
set "SCRIPT_DIR=%~dp0"
set "REPO_DIR=%SCRIPT_DIR%.."

REM Set installation directory (defaults to user's AppData)
if "%INSTALL_DIR%"=="" (
    set "INSTALL_DIR=%LOCALAPPDATA%\DnDInitiativeTracker"
)

echo Installation directory: %INSTALL_DIR%
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Python is not installed or not in PATH.
    echo Please install Python 3.9 or higher from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

REM Check Python version
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set "PYTHON_VERSION=%%v"
echo Found Python %PYTHON_VERSION%

REM Verify Python version is 3.9 or higher
python -c "import sys; exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Python 3.9 or higher is required.
    echo Current version: %PYTHON_VERSION%
    pause
    exit /b 1
)

echo.
echo Creating installation directory...
if not exist "%INSTALL_DIR%" (
    mkdir "%INSTALL_DIR%"
)

echo Copying application files...
xcopy "%REPO_DIR%\*" "%INSTALL_DIR%\" /E /I /Y /EXCLUDE:%SCRIPT_DIR%exclude-files.txt >nul 2>&1
if not exist "%SCRIPT_DIR%exclude-files.txt" (
    REM If exclude file doesn't exist, copy manually excluding specific folders
    xcopy "%REPO_DIR%\*.py" "%INSTALL_DIR%\" /Y >nul
    xcopy "%REPO_DIR%\*.txt" "%INSTALL_DIR%\" /Y >nul
    xcopy "%REPO_DIR%\*.md" "%INSTALL_DIR%\" /Y >nul
    xcopy "%REPO_DIR%\Monsters" "%INSTALL_DIR%\Monsters\" /E /I /Y >nul
    xcopy "%REPO_DIR%\Spells" "%INSTALL_DIR%\Spells\" /E /I /Y >nul
    xcopy "%REPO_DIR%\assets" "%INSTALL_DIR%\assets\" /E /I /Y >nul
    xcopy "%REPO_DIR%\scripts" "%INSTALL_DIR%\scripts\" /E /I /Y >nul
    if exist "%REPO_DIR%\players" xcopy "%REPO_DIR%\players" "%INSTALL_DIR%\players\" /E /I /Y >nul
    if exist "%REPO_DIR%\presets" xcopy "%REPO_DIR%\presets" "%INSTALL_DIR%\presets\" /E /I /Y >nul
)

echo Creating logs directory...
if not exist "%INSTALL_DIR%\logs" (
    mkdir "%INSTALL_DIR%\logs"
)

echo.
echo Setting up Python virtual environment...
set "VENV_READY=0"
if not exist "%INSTALL_DIR%\.venv" (
    python -m venv "%INSTALL_DIR%\.venv"
    if %ERRORLEVEL% NEQ 0 (
        echo WARNING: Failed to create virtual environment.
        echo Continuing without virtual environment...
    ) else (
        echo Virtual environment created successfully.
        set "VENV_READY=1"
    )
) else (
    echo Virtual environment already exists.
    set "VENV_READY=1"
)

REM Install dependencies if virtual environment was created
set "DEPS_READY=0"
if exist "%INSTALL_DIR%\.venv\Scripts\python.exe" (
    echo.
    echo Installing Python dependencies...
    REM Upgrade pip first
    "%INSTALL_DIR%\.venv\Scripts\python.exe" -m pip install --upgrade pip >nul 2>&1
    "%INSTALL_DIR%\.venv\Scripts\python.exe" -m pip install -r "%INSTALL_DIR%\requirements.txt"
    if %ERRORLEVEL% NEQ 0 (
        echo WARNING: Failed to install some dependencies.
        echo The executable will not be built. You may need to install them manually.
    ) else (
        echo Dependencies installed successfully.
        echo Verifying installed dependencies...
        "%INSTALL_DIR%\.venv\Scripts\python.exe" -c "import fastapi,uvicorn,yaml,PIL,qrcode"
        if %ERRORLEVEL% NEQ 0 (
            echo ERROR: Dependency verification failed. Please reinstall dependencies and rerun the installer.
            pause
            exit /b 1
        ) else (
            echo Dependencies verified successfully.
            set "DEPS_READY=1"
        )
    )
)

echo.
echo Creating launcher script...
(
    echo @echo off
    echo REM D&D Initiative Tracker Launcher
    echo setlocal
    echo.
    echo set "APP_DIR=%%~dp0"
    echo set "LOG_DIR=%%APP_DIR%%logs"
    echo.
    echo if not exist "%%LOG_DIR%%" mkdir "%%LOG_DIR%%"
    echo.
    echo cd /d "%%APP_DIR%%"
    echo.
    echo REM Try to use pythonw.exe to hide console window
    echo if exist "%%APP_DIR%%.venv\Scripts\pythonw.exe" ^(
    echo     start "" "%%APP_DIR%%.venv\Scripts\pythonw.exe" "%%APP_DIR%%dnd_initative_tracker.py"
    echo ^) else if exist "%%APP_DIR%%.venv\Scripts\python.exe" ^(
    echo     "%%APP_DIR%%.venv\Scripts\python.exe" "%%APP_DIR%%dnd_initative_tracker.py"
    echo ^) else ^(
    echo     python "%%APP_DIR%%dnd_initative_tracker.py"
    echo ^)
    echo.
    echo endlocal
) > "%INSTALL_DIR%\launch-dnd-tracker.bat"

echo.
echo Creating icon file...
if exist "%INSTALL_DIR%\.venv\Scripts\python.exe" (
    "%INSTALL_DIR%\.venv\Scripts\python.exe" "%INSTALL_DIR%\scripts\create_icon.py" >nul 2>&1
)

echo.
echo Building Windows executable...
set "EXE_PATH=%INSTALL_DIR%\DNDInitiativeTracker.exe"
set "EXE_READY=0"
if "%VENV_READY%"=="1" if "%DEPS_READY%"=="1" (
    echo Installing PyInstaller...
    "%INSTALL_DIR%\.venv\Scripts\python.exe" -m pip install pyinstaller
    if %ERRORLEVEL% NEQ 0 (
        echo WARNING: Failed to install PyInstaller. Skipping EXE build.
    ) else (
        echo Building executable with icon and no console...
        set "ICON_ARG="
        if exist "%INSTALL_DIR%\assets\icon.ico" (
            set "ICON_ARG=--icon=%INSTALL_DIR%\assets\icon.ico"
        )
        "%INSTALL_DIR%\.venv\Scripts\python.exe" -m PyInstaller --noconsole --onefile %ICON_ARG% --name=DNDInitiativeTracker --distpath="%INSTALL_DIR%" --workpath="%INSTALL_DIR%\build" --specpath="%INSTALL_DIR%" --clean "%INSTALL_DIR%\launcher.py"
        if %ERRORLEVEL% EQU 0 if exist "%EXE_PATH%" (
            echo Executable built successfully.
            set "EXE_READY=1"
            if exist "%INSTALL_DIR%\build" rmdir /s /q "%INSTALL_DIR%\build"
            if exist "%INSTALL_DIR%\DNDInitiativeTracker.spec" del /q "%INSTALL_DIR%\DNDInitiativeTracker.spec"
        ) else (
            echo WARNING: Executable build failed. Falling back to batch launcher.
        )
    )
) else (
    echo WARNING: Skipping EXE build because the virtual environment or dependencies are not ready.
)

echo.
echo Creating desktop shortcut...
set "SHORTCUT_NAME=D&D Initiative Tracker.lnk"
set "DESKTOP=%USERPROFILE%\Desktop"
set "START_MENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs"
set "ICON_PATH=%INSTALL_DIR%\assets\icon.ico"
set "SHORTCUT_TARGET=%INSTALL_DIR%\launch-dnd-tracker.bat"
if "%EXE_READY%"=="1" (
    set "SHORTCUT_TARGET=%EXE_PATH%"
)

REM Use PowerShell to create shortcut with icon
if exist "%ICON_PATH%" (
    powershell -Command "$WS = New-Object -ComObject WScript.Shell; $SC = $WS.CreateShortcut('%DESKTOP%\%SHORTCUT_NAME%'); $SC.TargetPath = '%SHORTCUT_TARGET%'; $SC.WorkingDirectory = '%INSTALL_DIR%'; $SC.Description = 'D&D Initiative Tracker'; $SC.IconLocation = '%ICON_PATH%'; $SC.Save()" >nul 2>&1
) else (
    powershell -Command "$WS = New-Object -ComObject WScript.Shell; $SC = $WS.CreateShortcut('%DESKTOP%\%SHORTCUT_NAME%'); $SC.TargetPath = '%SHORTCUT_TARGET%'; $SC.WorkingDirectory = '%INSTALL_DIR%'; $SC.Description = 'D&D Initiative Tracker'; $SC.Save()" >nul 2>&1
)

if %ERRORLEVEL% EQU 0 (
    echo Desktop shortcut created successfully.
) else (
    echo WARNING: Failed to create desktop shortcut.
)

REM Create Start Menu shortcut
if exist "%ICON_PATH%" (
    powershell -Command "$WS = New-Object -ComObject WScript.Shell; $SC = $WS.CreateShortcut('%START_MENU%\%SHORTCUT_NAME%'); $SC.TargetPath = '%SHORTCUT_TARGET%'; $SC.WorkingDirectory = '%INSTALL_DIR%'; $SC.Description = 'D&D Initiative Tracker'; $SC.IconLocation = '%ICON_PATH%'; $SC.Save()" >nul 2>&1
) else (
    powershell -Command "$WS = New-Object -ComObject WScript.Shell; $SC = $WS.CreateShortcut('%START_MENU%\%SHORTCUT_NAME%'); $SC.TargetPath = '%SHORTCUT_TARGET%'; $SC.WorkingDirectory = '%INSTALL_DIR%'; $SC.Description = 'D&D Initiative Tracker'; $SC.Save()" >nul 2>&1
)

if %ERRORLEVEL% EQU 0 (
    echo Start Menu shortcut created successfully.
) else (
    echo WARNING: Failed to create Start Menu shortcut.
)

echo.
echo Registering with Windows Add/Remove Programs...
set "UNINSTALL_SCRIPT=%INSTALL_DIR%\scripts\uninstall-windows.bat"
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\DnDInitiativeTracker" /v DisplayName /t REG_SZ /d "D&D Initiative Tracker" /f >nul 2>&1
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\DnDInitiativeTracker" /v DisplayVersion /t REG_SZ /d "1.0.0" /f >nul 2>&1
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\DnDInitiativeTracker" /v Publisher /t REG_SZ /d "D&D Initiative Tracker" /f >nul 2>&1
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\DnDInitiativeTracker" /v InstallLocation /t REG_SZ /d "%INSTALL_DIR%" /f >nul 2>&1
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\DnDInitiativeTracker" /v UninstallString /t REG_SZ /d "cmd.exe /c \"\"%UNINSTALL_SCRIPT%\"\"" /f >nul 2>&1
if exist "%ICON_PATH%" (
    reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\DnDInitiativeTracker" /v DisplayIcon /t REG_SZ /d "%ICON_PATH%" /f >nul 2>&1
)
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\DnDInitiativeTracker" /v NoModify /t REG_DWORD /d 1 /f >nul 2>&1
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\DnDInitiativeTracker" /v NoRepair /t REG_DWORD /d 1 /f >nul 2>&1

if %ERRORLEVEL% EQU 0 (
    echo Registered with Add/Remove Programs successfully.
) else (
    echo WARNING: Failed to register with Add/Remove Programs.
)

echo.
echo ====================================================
echo Installation Complete!
echo ====================================================
echo.
echo Application installed to: %INSTALL_DIR%
echo.
echo You can now launch the tracker using:
echo   - Desktop shortcut: "D&D Initiative Tracker"
echo   - Start Menu: Search for "D&D Initiative Tracker"
echo   - Command line: %INSTALL_DIR%\launch-dnd-tracker.bat
echo.
echo Logs will be stored in: %INSTALL_DIR%\logs\
echo.
echo ====================================================
pause
