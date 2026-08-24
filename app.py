#!/usr/bin/env python3
"""Media Downloader - desktop entry point.

Two ways to reach the same UI:

  native  (default)  pywebview opens web/index.html from disk and talks to the
                     core through a js_api bridge. No socket is opened, so
                     macOS never asks for local-network permission.
  browser (--browser) a loopback HTTP server serves the same page. Handy for
                     development, and the fallback when pywebview is missing.
"""

import argparse
import signal
import sys
import threading
import webbrowser

from core import EventBus, JobManager
from core import settings as settings_store
from core.appinfo import APP_NAME, APP_VERSION, resource_path
from core.ffmpeg import extend_path
from server import Api, Bridge, LocalServer

WINDOW_WIDTH = 780
WINDOW_HEIGHT = 900
MIN_SIZE = (560, 620)
BACKGROUND = "#0e0e12"


def build_core():
    """Create the UI-agnostic objects both transports sit on top of."""
    extend_path()

    current = settings_store.load()
    bus = EventBus()
    jobs = JobManager(bus=bus, max_parallel=current["max_parallel"])
    return Api(jobs), bus


def run_native(api, bus, hidden=False):
    """Open the UI in a native window. Returns False if pywebview is missing."""
    try:
        import webview
    except ImportError:
        return False

    index = resource_path("web", "index.html")
    if not index.exists():
        return False

    bridge = Bridge(api, bus)
    window = webview.create_window(
        APP_NAME,
        index.as_uri(),          # file:// keeps pywebview from starting a server
        js_api=bridge,
        width=WINDOW_WIDTH,
        height=WINDOW_HEIGHT,
        min_size=MIN_SIZE,
        background_color=BACKGROUND,
        text_select=True,
        hidden=hidden,
    )

    folder_dialog = getattr(getattr(webview, "FileDialog", None), "FOLDER", 20)

    def pick_folder(initial=None):
        """Native NSOpenPanel - no Apple Events permission required."""
        result = window.create_file_dialog(folder_dialog, directory=initial or "")
        if not result:
            return None
        return result[0] if isinstance(result, (list, tuple)) else result

    api.folder_picker = pick_folder
    bridge.attach(window)

    icon = resource_path("assets", "icon.png")
    try:
        webview.start(icon=str(icon) if icon.exists() else None)  # blocks
    finally:
        bridge.stop()
    return True


def run_browser(api, bus, port=0, open_page=True):
    """Serve the UI over loopback HTTP and hand it to the default browser."""
    server = LocalServer(resource_path("web"), api, bus, port=port)
    server.start()

    print(f"{APP_NAME} v{APP_VERSION}")
    print(f"UI:  {server.url}", flush=True)
    print("To'xtatish uchun Ctrl+C bosing.")

    if open_page:
        webbrowser.open(server.url)

    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())

    try:
        stop.wait()
    finally:
        server.stop()


def main(argv=None):
    parser = argparse.ArgumentParser(description=f"{APP_NAME} v{APP_VERSION}")
    parser.add_argument("--browser", action="store_true",
                        help="Native oyna o'rniga brauzerda ochish")
    parser.add_argument("--port", type=int, default=0,
                        help="HTTP portni belgilash (0 = avtomatik)")
    parser.add_argument("--no-open", action="store_true",
                        help="Serverni ishga tushirish, lekin UI ochilmasin")
    parser.add_argument("--hidden", action="store_true",
                        help="Native oynani ko'rsatmasdan ishga tushirish (test uchun)")
    args = parser.parse_args(argv)

    api, bus = build_core()

    try:
        if args.browser or args.no_open:
            run_browser(api, bus, port=args.port, open_page=not args.no_open)
        elif not run_native(api, bus, hidden=args.hidden):
            run_browser(api, bus, port=args.port)
    except KeyboardInterrupt:
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
