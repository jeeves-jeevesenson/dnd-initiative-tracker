@echo off
REM D&D Initiative Tracker - Windows Uninstaller

setlocal EnableDelayedExpansion

echo ====================================================
echo D&D Initiative Tracker - Windows Uninstaller
echo ====================================================
echo.

REM Set installation directory
if "%INSTALL_DIR%"=="" (
    set "INSTALL_DIR=%LOCALAPPDATA%\DnDInitiativeTracker"
)

echo This will remove the D&D Initiative Tracker from your system.
echo Installation directory: %INSTALL_DIR%
echo.
echo WARNING: This will delete all files in the installation directory,
echo including any custom configurations, saved presets, and logs.
echo.
set /p CONFIRM="Are you sure you want to continue? (Y/N): "

if /I not "%CONFIRM%"=="Y" (
    echo.
    echo Uninstallation cancelled.
    pause
    exit /b 0
)

echo.
echo Removing application files...

if exist "%INSTALL_DIR%" (
    echo Deleting %INSTALL_DIR%...
    rmdir /S /Q "%INSTALL_DIR%"
    if %ERRORLEVEL% EQU 0 (
        echo Application files removed successfully.
    ) else (
        echo WARNING: Failed to remove some files. You may need to delete manually.
    )
) else (
    echo Application directory not found. Already uninstalled?
)

echo.
echo Removing shortcuts...

REM Remove desktop shortcut
set "DESKTOP=%USERPROFILE%\Desktop"
set "SHORTCUT_NAME=D&D Initiative Tracker.lnk"

if exist "%DESKTOP%\%SHORTCUT_NAME%" (
    del "%DESKTOP%\%SHORTCUT_NAME%"
    echo Desktop shortcut removed.
) else (
    echo Desktop shortcut not found.
)

REM Remove Start Menu shortcut
set "START_MENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs"
if exist "%START_MENU%\%SHORTCUT_NAME%" (
    del "%START_MENU%\%SHORTCUT_NAME%"
    echo Start Menu shortcut removed.
) else (
    echo Start Menu shortcut not found.
)

echo.
echo ====================================================
echo Uninstallation Complete!
echo ====================================================
echo.
echo D&D Initiative Tracker has been removed from your system.
echo.
pause
