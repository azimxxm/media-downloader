"""FFmpeg discovery.

GUI apps launched from Finder inherit a minimal PATH, so we look in the usual
Homebrew/MacPorts locations as well as any binary bundled with the app.
"""

import os
import shutil
import subprocess
import sys
from functools import lru_cache

from .appinfo import resource_path

COMMON_BIN_DIRS = (
    "/opt/homebrew/bin",
    "/usr/local/bin",
    "/opt/local/bin",
    "/usr/bin",
    "/bin",
    "/usr/sbin",
    "/sbin",
)


def extend_path():
    """Add the usual binary directories to PATH so shutil.which() can find them."""
    current = os.environ.get("PATH", "")
    parts = current.split(os.pathsep) if current else []
    for directory in COMMON_BIN_DIRS:
        if directory not in parts and os.path.isdir(directory):
            parts.append(directory)
    os.environ["PATH"] = os.pathsep.join(parts)


def _bundled(name):
    """Path to a binary shipped inside the app bundle, if present."""
    suffix = ".exe" if sys.platform == "win32" else ""
    candidate = resource_path("bin", name + suffix)
    if candidate.exists() and os.access(candidate, os.X_OK):
        return str(candidate)
    return None


@lru_cache(maxsize=None)
def find_binary(name):
    """Locate ffmpeg/ffprobe. Bundled copy wins, then PATH, then known dirs."""
    bundled = _bundled(name)
    if bundled:
        return bundled

    extend_path()
    found = shutil.which(name)
    if found:
        return found

    suffix = ".exe" if sys.platform == "win32" else ""
    for directory in COMMON_BIN_DIRS:
        candidate = os.path.join(directory, name + suffix)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate

    return None


def ffmpeg_location():
    """Directory holding ffmpeg, in the form yt-dlp expects (or None)."""
    binary = find_binary("ffmpeg")
    return os.path.dirname(binary) if binary else None


def check():
    """Return (is_available, message, path)."""
    binary = find_binary("ffmpeg")
    if not binary:
        return (
            False,
            "FFmpeg o'rnatilmagan. Video va audio birlashtirish uchun kerak.\n"
            "O'rnatish: brew install ffmpeg",
            None,
        )

    try:
        result = subprocess.run(
            [binary, "-version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"FFmpeg tekshirishda xatolik: {exc}", binary

    if result.returncode != 0:
        return False, "FFmpeg ishga tushmadi.", binary

    first_line = (result.stdout or "").splitlines()
    version = first_line[0] if first_line else "ffmpeg"
    return True, version, binary


def reset_cache():
    """Forget cached lookups (used after the user installs FFmpeg)."""
    find_binary.cache_clear()
