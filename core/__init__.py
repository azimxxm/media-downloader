"""Pure-Python core of Media Downloader.

Nothing in this package imports a UI framework, so it can be driven from the
HTTP server, a CLI, or a test suite without changes.
"""

from .appinfo import APP_ID, APP_NAME, APP_VERSION, resource_path, support_dir
from .errors import DownloadCancelled, translate_error
from .events import EventBus
from .jobs import JobManager
from .media import analyze, analyze_playlist, analyze_single

__all__ = [
    "APP_ID",
    "APP_NAME",
    "APP_VERSION",
    "DownloadCancelled",
    "EventBus",
    "JobManager",
    "analyze",
    "analyze_playlist",
    "analyze_single",
    "resource_path",
    "support_dir",
    "translate_error",
]
