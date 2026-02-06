# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path


project_root = Path(__file__).resolve().parents[2]
app_name = "DnDInitiativeTracker"
entry_script = project_root / "dnd_initative_tracker.py"
icon_path = project_root / "assets" / "icon.ico"

datas = [
    (str(project_root / "Monsters"), "Monsters"),
    (str(project_root / "Spells"), "Spells"),
    (str(project_root / "assets"), "assets"),
    (str(project_root / "presets"), "presets"),
    (str(project_root / "players"), "players"),
    (str(project_root / "VERSION"), "."),
]

a = Analysis(
    [str(entry_script)],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name=app_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(icon_path) if icon_path.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name=app_name,
)
