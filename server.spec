# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for PharmaServer.exe (v1.3.0).

One-file console build of server.py — the live-data server the
standalone HTML file (Pharma-Purchase-Assistant.html, opened as file://)
calls at http://127.0.0.1:5000. No Python install needed on the pharmacy PC.

The dashboard HTML (web/index.html) is bundled as data, so the frozen
exe serves it from its own temp folder exactly like server.py does.

Build on Windows (CI does this):  pyinstaller --noconfirm --clean server.spec
Output: dist/PharmaServer.exe
"""

block_cipher = None

a = Analysis(
    ["server.py"],
    pathex=[],
    binaries=[],
    datas=[("web", "web")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="PharmaServer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
