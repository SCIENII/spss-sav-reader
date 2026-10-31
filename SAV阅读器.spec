# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\Users\\SCIEN\\Desktop\\SAV阅读器\\app\\main.py'],
    pathex=[],
    binaries=[],
    datas=[('C:\\Users\\SCIEN\\Desktop\\SAV阅读器\\app\\icon.ico', '.')],
    hiddenimports=['pyreadstat', 'pyreadstat._pyreadstat', 'pandas', 'customtkinter', 'tkinterdnd2', 'PIL', 'PIL._tkinter_finder', 'queue', 'threading'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SAV阅读器',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['C:\\Users\\SCIEN\\Desktop\\SAV阅读器\\app\\icon.ico'],
)
