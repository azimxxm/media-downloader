"""App-level constants and resource resolution (works in dev and frozen builds)."""

import sys
from pathlib import Path

APP_NAME = "Media Downloader"
APP_ID = "MediaDownloader"
APP_VERSION = "2.0.0"


def is_frozen():
    """True when running inside a PyInstaller bundle."""
    return getattr(sys, "frozen", False)


def resource_dir():
    """Root folder that holds bundled data files (web/, assets/, bin/)."""
    if is_frozen():
        # PyInstaller unpacks data files into _MEIPASS
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def resource_path(*parts):
    """Absolute path to a bundled resource."""
    return resource_dir().joinpath(*parts)


def support_dir():
    """Per-user writable folder for settings and logs."""
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / APP_ID
    elif sys.platform == "win32":
        base = Path.home() / "AppData" / "Roaming" / APP_ID
    else:
        base = Path.home() / ".config" / APP_ID.lower()
    base.mkdir(parents=True, exist_ok=True)
    return base
