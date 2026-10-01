# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import re

root = Path(SPECPATH)
datas = [(str(root / 'resources' / name), 'resources')
         for name in ('background.png', 'icon.png', 'icon.ico', 'bridge.js')]

a = Analysis(
    [str(root / 'main.py')], pathex=[str(root)], binaries=[], datas=datas,
    hiddenimports=['PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebChannel'],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['tkinter', 'PyQt5', 'PyQt6'], noarchive=False,
)
# The pinned Qt wheel imports Windows' unversioned ICU C API. Some build
# environments have Poppler/Conda ICU DLLs on PATH with incompatible exports.
# Exclude those shadow copies and let Qt load the Windows system ICU library.
a.binaries = [entry for entry in a.binaries
              if not re.fullmatch(r'(icu(?:uc|in)?|icudt\d+)\.dll', Path(entry[0]).name, re.I)]
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name='PixivBatchBookmark',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=False,
    icon=str(root / 'resources' / 'icon.ico'),
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='PixivBatchBookmark')
