import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """Keep every test away from the developer's real settings file."""
    from core import settings as settings_store

    monkeypatch.setattr(settings_store, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setitem(settings_store.DEFAULTS, "youtube_dir", str(tmp_path / "yt"))
    monkeypatch.setitem(settings_store.DEFAULTS, "instagram_dir", str(tmp_path / "ig"))
    yield


@pytest.fixture(autouse=True)
def clear_metadata_cache():
    from core.cache import metadata_cache

    metadata_cache.clear()
    yield
    metadata_cache.clear()
