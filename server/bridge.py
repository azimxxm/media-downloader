"""Native transport: exposes the API to the page as `window.pywebview.api`.

Used by the packaged desktop app. Because it needs no socket, macOS never
shows the "find devices on your local network" permission prompt that any
listening TCP port triggers on recent releases.
"""

import json
import threading

from core.errors import translate_error

from . import routes


class Bridge:
    """js_api object handed to pywebview.create_window(js_api=...)."""

    def __init__(self, api, bus):
        self._api = api
        self._bus = bus
        self._window = None
        self._routes = routes.build(api)
        self._stop = threading.Event()

    # ------------------------------------------------------------ js -> py

    def call(self, path, payload=None):
        """Single entry point mirroring one HTTP request."""
        if path == "/api/settings" and not payload:
            handler = self._api.get_settings
        else:
            handler = self._routes.get(path)

        if handler is None:
            return {"__error": f"Unknown endpoint: {path}"}

        try:
            status, body = handler(payload or {})
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI as text
            return {"__error": translate_error(exc)}

        if status >= 400:
            return {"__error": body.get("error", f"HTTP {status}")}
        return body

    # ------------------------------------------------------------ py -> js

    def attach(self, window):
        """Start pushing core events into the page."""
        self._window = window
        threading.Thread(target=self._pump, daemon=True).start()

    def stop(self):
        self._stop.set()
        self._bus.publish({"type": "shutdown"})

    def _pump(self):
        listener = self._bus.subscribe()
        try:
            while not self._stop.is_set():
                event = listener.get()
                if event.get("type") == "shutdown":
                    break
                payload = json.dumps(event, ensure_ascii=False, default=str)
                try:
                    # evaluate_js blocks until the page is ready, so events
                    # raised during start-up are delivered rather than lost.
                    self._window.evaluate_js(f"window.__mdlEvent({payload})")
                except Exception:  # noqa: BLE001 - window closed mid-flight
                    break
        finally:
            self._bus.unsubscribe(listener)
