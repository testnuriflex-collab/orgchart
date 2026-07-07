# PyInstaller one-folder build.
#   macOS: pyinstaller packaging/org-chart-studio.spec --noconfirm --clean  (-> .app 번들까지 생성)
#   Windows: 동일 스펙을 windows-latest에서 실행 (.github/workflows/build-windows.yml 참조).
# PyInstaller는 대상 OS 위에서 실행해야 하므로(크로스 컴파일 불가) macOS에서는 로컬 빌드,
# Windows exe는 GitHub Actions windows-latest 러너로 생성한다.

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None
root = Path(SPECPATH).resolve().parent

# 플랫폼별 아이콘: macOS 빌드는 .icns, Windows 빌드는 .ico만 EXE에 임베드 가능.
_icon_path = root / "resources" / "icons" / ("app.icns" if sys.platform == "darwin" else "app.ico")
APP_ICON = str(_icon_path) if _icon_path.exists() else None
VERSION_FILE = str(root / "packaging" / "version_info.txt") if sys.platform.startswith("win") else None

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
    icon=APP_ICON,
    version=VERSION_FILE,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="START-Windows" if sys.platform.startswith("win") else "OrgChartStudio",
)

# macOS 전용 .app 번들 — Windows 등 다른 OS에서는 PyInstaller가 자동으로 건너뛴다.
app = BUNDLE(
    coll,
    name="OrgChartStudio.app",
    icon=APP_ICON,
    bundle_identifier="com.orgchartstudio.app",
    info_plist={
        "CFBundleName": "조직도 Studio",
        "CFBundleDisplayName": "조직도 Studio",
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion": "0.1.0",
        "NSHighResolutionCapable": True,
        "NSHumanReadableCopyright": "Copyright (c) 2026 OrgChartStudio Project",
    },
)
