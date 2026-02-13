# Creating a Windows Executable (Optional)

If you want to create a standalone Windows executable (.exe) that doesn't require Python to be installed, you can use **PyInstaller**. This is an **optional** advanced feature for users who want to distribute the application without requiring Python installation.

## Using PyInstaller (Recommended)

### Prerequisites

- Python 3.9+ installed
- All dependencies from `requirements.txt` installed
- PyInstaller package

### Installation

```cmd
# Install PyInstaller
pip install pyinstaller
```

### Creating the Executable

```cmd
# Navigate to the repository directory
cd dnd-initiative-tracker

# Create a single executable file (larger file, but self-contained)
pyinstaller --onefile --windowed --name "DnD-Initiative-Tracker" ^
    --icon=assets/graphic-192.png ^
    --add-data "Monsters;Monsters" ^
    --add-data "Spells;Spells" ^
    --add-data "assets;assets" ^
    dnd_initative_tracker.py

# Note: PyInstaller will convert PNG to .ico automatically, but for best results
# consider converting to .ico format first using a tool like ImageMagick or online converters

# OR create a directory bundle (smaller main exe, but includes supporting files)
pyinstaller --onedir --windowed --name "DnD-Initiative-Tracker" ^
    --icon=assets/graphic-192.png ^
    --add-data "Monsters;Monsters" ^
    --add-data "Spells;Spells" ^
    --add-data "assets;assets" ^
    dnd_initative_tracker.py
```

### Output

- **Single file mode (`--onefile`)**: Creates `dist/DnD-Initiative-Tracker.exe` (100+ MB)
- **Directory mode (`--onedir`)**: Creates `dist/DnD-Initiative-Tracker/` folder with the executable and supporting files

### Notes

- The single-file executable is slower to start (needs to extract files on each run)
- The directory bundle is faster but requires all files to be distributed together
- The executable will be quite large (100-200 MB) due to Python runtime and dependencies
- Test the executable thoroughly before distribution

## Why Not Include Pre-built Executables?

Pre-built executables are not included in this repository for several reasons:

1. **Large file size**: Executables are 100+ MB and not suitable for version control
2. **Security concerns**: Users should build from source for security verification
3. **Platform variations**: Different Windows versions may need different builds
4. **Maintenance overhead**: Every code change would require rebuilding and testing executables
5. **Python flexibility**: Running from Python source allows for easier customization

## Recommendations

For most users, we recommend:
- **Regular users**: Use the automated installer scripts (`install-windows.bat` or `install-windows.ps1`)
- **Developers**: Run directly with Python for easier debugging and development
- **Distribution**: Only create executables if you need to distribute to non-technical users without Python

The installer scripts provide a good balance between ease of use and flexibility.
