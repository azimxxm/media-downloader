# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Media Downloader (macOS .app bundle).

Build from the project root:
    pyinstaller packaging/MediaDownloader.spec --noconfirm
"""

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent          # noqa: F821 - SPECPATH is injected
sys.path.insert(0, str(ROOT))
from core.appinfo import APP_NAME, APP_VERSION  # noqa: E402

BUNDLE_ID = "com.github.azimxxm.mediadownloader"

# yt-dlp resolves extractors dynamically, so PyInstaller cannot see them.
hiddenimports = collect_submodules("yt_dlp")

datas = [
    (str(ROOT / "web"), "web"),
    (str(ROOT / "assets" / "icon.png"), "assets"),
]
datas += collect_data_files("yt_dlp")

# Ship ffmpeg/ffprobe inside the bundle when explicitly asked for, so a fresh
# Mac needs no Homebrew. See packaging/build_macos.sh --with-ffmpeg.
binaries = []
if os.environ.get("MDL_BUNDLE_FFMPEG") == "1":
    for tool in ("ffmpeg", "ffprobe"):
        staged = ROOT / "packaging" / "bin" / tool
        if not staged.exists():
            raise SystemExit(f"MDL_BUNDLE_FFMPEG=1 but {staged} is missing")
        binaries.append((str(staged), "bin"))

analysis = Analysis(                   # noqa: F821
    [str(ROOT / "app.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter", "flet", "flet_desktop", "flet_core",
        "PIL", "numpy", "matplotlib", "pandas", "scipy",
        "pytest", "setuptools", "pip", "wheel",
        "test", "unittest", "pydoc_data",
    ],
    noarchive=False,
    optimize=2,
)

pyz = PYZ(analysis.pure)               # noqa: F821

exe = EXE(                             # noqa: F821
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                         # UPX corrupts macOS code signatures
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,                  # host architecture
    codesign_identity=None,            # signing happens in build_macos.sh
    entitlements_file=None,
    icon=str(ROOT / "assets" / "icon.icns"),
)

collection = COLLECT(                  # noqa: F821
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)

app = BUNDLE(                          # noqa: F821
    collection,
    name=f"{APP_NAME}.app",
    icon=str(ROOT / "assets" / "icon.icns"),
    bundle_identifier=BUNDLE_ID,
    version=APP_VERSION,
    info_plist={
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleShortVersionString": APP_VERSION,
        "CFBundleVersion": APP_VERSION,
        "LSMinimumSystemVersion": "11.0",
        "LSApplicationCategoryType": "public.app-category.utilities",
        "NSHighResolutionCapable": True,
        "NSHumanReadableCopyright": "MIT License",
        # The UI is served from 127.0.0.1 over plain HTTP; this is the narrow
        # ATS exemption for that, rather than NSAllowsArbitraryLoads.
        "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
        "NSDownloadsFolderUsageDescription":
            "Yuklab olingan video va audio fayllar shu papkaga saqlanadi.",
        "NSAppleEventsUsageDescription":
            "Papka tanlash oynasini ochish uchun kerak.",
    },
)
