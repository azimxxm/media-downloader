"""Persisted user settings (download folder, parallel limit, defaults)."""

import json
import threading

from .appinfo import support_dir
from .system import default_download_dir

SETTINGS_FILE = support_dir() / "settings.json"

DEFAULTS = {
    "youtube_dir": default_download_dir("youtube"),
    "instagram_dir": default_download_dir("instagram"),
    "max_parallel": 2,
    "default_mode": "video",
    "subtitle_lang": "en",
}

_lock = threading.Lock()


def load():
    """Read settings from disk, filling in any missing key with its default."""
    data = dict(DEFAULTS)
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as handle:
            stored = json.load(handle)
        if isinstance(stored, dict):
            data.update({key: stored[key] for key in DEFAULTS if key in stored})
    except (OSError, ValueError):
        pass  # first run, or a corrupted file - fall back to defaults
    return data


def save(patch):
    """Merge a partial dict into the stored settings and return the result."""
    with _lock:
        data = load()
        data.update({key: patch[key] for key in DEFAULTS if key in patch})

        try:
            SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(SETTINGS_FILE, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2)
        except OSError:
            pass  # settings are a convenience; never break the app over them

        return data
