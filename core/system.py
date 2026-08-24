"""Thin OS integration layer: Finder reveal, folder picker, clipboard."""

import os
import subprocess
import sys
from pathlib import Path


def is_macos():
    return sys.platform == "darwin"


def is_windows():
    return sys.platform == "win32"


def default_download_dir(platform="youtube"):
    """Default destination folder for a given source platform."""
    base = Path.home() / "Downloads"
    if platform == "instagram":
        base = base / "Instagram"
    return str(base)


def ensure_dir(path):
    """Create the folder if needed and return it as a string."""
    directory = Path(path).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    return str(directory)


def reveal(path):
    """Select the file in Finder / Explorer / the Linux file manager."""
    target = Path(path)
    if not target.exists():
        return False

    try:
        if is_macos():
            subprocess.run(["open", "-R", str(target)], check=False)
        elif is_windows():
            subprocess.run(["explorer", "/select,", str(target)], check=False)
        else:
            subprocess.run(["xdg-open", str(target.parent)], check=False)
        return True
    except OSError:
        return False


def open_folder(path):
    """Open a folder in the system file manager."""
    target = Path(path)
    if not target.exists():
        return False

    try:
        if is_macos():
            subprocess.run(["open", str(target)], check=False)
        elif is_windows():
            os.startfile(str(target))  # noqa: S606 - Windows-only API
        else:
            subprocess.run(["xdg-open", str(target)], check=False)
        return True
    except OSError:
        return False


def read_clipboard():
    """Read text from the system clipboard. Returns '' when unavailable."""
    try:
        if is_macos():
            result = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=3)
            return result.stdout.strip()
        if is_windows():
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                capture_output=True, text=True, timeout=5,
            )
            return result.stdout.strip()
        result = subprocess.run(["xclip", "-o", "-selection", "clipboard"],
                                capture_output=True, text=True, timeout=3)
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def choose_folder(initial=None):
    """Native folder picker. Returns the chosen path or None if cancelled.

    On macOS this uses osascript so it works with any UI shell.
    """
    if not is_macos():
        return None

    start = initial or str(Path.home() / "Downloads")
    script = (
        f'set startFolder to POSIX file "{start}" as alias\n'
        'set chosen to choose folder with prompt "Yuklab olish papkasini tanlang" '
        "default location startFolder\n"
        "POSIX path of chosen"
    )

    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if result.returncode != 0:
        return None  # user cancelled

    picked = result.stdout.strip()
    return picked.rstrip("/") if picked else None
