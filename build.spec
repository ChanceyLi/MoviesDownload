# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller build specification for MoviesDownload.

Usage (run from the project root):
    pip install pyinstaller
    pyinstaller build.spec

The resulting Windows executable will be placed in the `dist/` folder.
"""

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        "searcher",
        "downloader",
        "tkinter",
        "tkinter.ttk",
        "tkinter.font",
        "tkinter.messagebox",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="MoviesDownload",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # set True if you want a console window for debug
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,              # replace with path to an .ico file if desired
)
