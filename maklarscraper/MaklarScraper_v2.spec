# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
hiddenimports=collect_submodules("bs4")
a = Analysis(["maklarscraper.py"], pathex=[], binaries=[], datas=[], hiddenimports=hiddenimports, hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="MaklarScraper_v2", debug=False, bootloader_ignore_signals=False, strip=False, upx=True, console=True)
