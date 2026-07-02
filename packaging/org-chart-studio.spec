# PyInstaller one-folder build:
# pyinstaller packaging/org-chart-studio.spec

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None
root = Path(SPECPATH).resolve().parent

a = Analysis(
    [str(root / "app" / "main.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[
        (str(root / "resources"), "resources"),
        (str(root / "app" / "db" / "migrations"), "app/db/migrations"),
        (str(root / "alembic.ini"), "."),
        (str(root / "DESIGN.md"), "."),
    ],
    hiddenimports=[
        "alembic",
        "logging.config",
        "openpyxl",
        "PySide6.QtPrintSupport",
        *collect_submodules("shiboken6"),
    ],
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
    [],
    exclude_binaries=True,
    name="OrgChartStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="OrgChartStudio",
)
