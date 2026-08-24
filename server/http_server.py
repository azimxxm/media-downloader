"""Minimal local HTTP + SSE server built on http.server.

Deliberately stdlib-only: no FastAPI, no uvicorn, no websockets package. That
keeps PyInstaller builds free of hidden-import surprises, which is the whole
reason this app moved off Flet.
"""

import json
import mimetypes
import queue
import secrets
import socketserver
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import routes

_SSE_HEARTBEAT = 15.0  # seconds between keep-alive comments


class _LoopbackHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer without the reverse-DNS lookup on bind.

    http.server calls socket.getfqdn() while binding, which on macOS goes out
    through mDNSResponder and makes the system show the "find devices on your
    local network" permission prompt - for a server that only ever listens on
    127.0.0.1. Skipping the lookup removes the prompt entirely.
    """

    daemon_threads = True
    allow_reuse_address = True

    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        self.server_name = self.server_address[0]
        self.server_port = self.server_address[1]


class LocalServer:
    """Serves the web UI and the JSON API on 127.0.0.1 with a random port."""

    def __init__(self, web_dir, api, bus, host="127.0.0.1", port=0):
        self.web_dir = Path(web_dir).resolve()
        self.api = api
        self.bus = bus
        self.host = host
        self.requested_port = port
        self.token = secrets.token_urlsafe(24)

        self._httpd = None
        self._thread = None
        self._stopping = threading.Event()

        self.routes = routes.build(api)

    # ------------------------------------------------------------------ url

    @property
    def port(self):
        return self._httpd.server_address[1] if self._httpd else None

    @property
    def url(self):
        return f"http://{self.host}:{self.port}/?token={self.token}"

    # -------------------------------------------------------------- control

    def start(self):
        """Bind, serve in a daemon thread, and return the entry URL."""
        handler = _make_handler(self)
        self._httpd = _LoopbackHTTPServer((self.host, self.requested_port), handler)

        self._thread = threading.Thread(
            target=self._httpd.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True
        )
        self._thread.start()
        return self.url

    def stop(self):
        self._stopping.set()
        self.bus.publish({"type": "shutdown"})
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None

    @property
    def stopping(self):
        return self._stopping.is_set()


def _make_handler(server):
    """Build a handler class bound to this LocalServer instance."""

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "MediaDownloader"
        sys_version = ""

        # -------------------------------------------------------- utilities

        def log_message(self, *_args):
            """Silence the default stderr access log."""

        def address_string(self):
            """Return the peer IP verbatim - no reverse DNS, ever."""
            return self.client_address[0]

        def _host_allowed(self):
            """Reject anything not addressed to our loopback origin."""
            host = (self.headers.get("Host") or "").split(":")[0]
            return host in ("127.0.0.1", "localhost", "[::1]", "::1")

        def _token_ok(self, query):
            supplied = self.headers.get("X-Auth-Token") or (query.get("token", [""])[0])
            return secrets.compare_digest(supplied or "", server.token)

        def _send_json(self, status, payload):
            body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self._write(body)

        def _send_bytes(self, status, body, content_type, cache="no-cache"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache)
            self.end_headers()
            self._write(body)

        def _write(self, data):
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                self.close_connection = True

        def _read_json(self):
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0:
                return {}
            try:
                raw = self.rfile.read(length)
                return json.loads(raw.decode("utf-8"))
            except (ValueError, OSError):
                return {}

        # ----------------------------------------------------------- static

        def _serve_static(self, path):
            if path in ("", "/"):
                path = "/index.html"

            target = (server.web_dir / path.lstrip("/")).resolve()
            if not str(target).startswith(str(server.web_dir)) or not target.is_file():
                self._send_json(404, {"error": "Not found"})
                return

            content_type, _ = mimetypes.guess_type(str(target))
            body = target.read_bytes()

            # The page needs the API token; inject it instead of exposing an
            # unauthenticated endpoint that hands it out.
            if target.name == "index.html":
                body = body.replace(b"__AUTH_TOKEN__", server.token.encode("utf-8"))

            self._send_bytes(200, body, content_type or "application/octet-stream")

        # -------------------------------------------------------------- SSE

        def _serve_events(self):
            listener = server.bus.subscribe()

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-transform")
            self.send_header("Connection", "close")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            self.close_connection = True

            try:
                self._sse_send({"type": "ready"})
                while not server.stopping:
                    try:
                        event = listener.get(timeout=_SSE_HEARTBEAT)
                    except queue.Empty:
                        self._write(b": ping\n\n")
                        self.wfile.flush()
                        continue

                    if event.get("type") == "shutdown":
                        break
                    self._sse_send(event)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass  # client navigated away
            finally:
                server.bus.unsubscribe(listener)

        def _sse_send(self, event):
            payload = json.dumps(event, ensure_ascii=False, default=str)
            self._write(f"data: {payload}\n\n".encode("utf-8"))
            self.wfile.flush()

        # ---------------------------------------------------------- verbs

        def _dispatch(self, method):
            if not self._host_allowed():
                self._send_json(403, {"error": "Forbidden host"})
                return

            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            path = parsed.path

            if not path.startswith("/api/"):
                if method == "GET":
                    self._serve_static(path)
                else:
                    self._send_json(405, {"error": "Method not allowed"})
                return

            if not self._token_ok(query):
                self._send_json(401, {"error": "Unauthorized"})
                return

            if path == "/api/events" and method == "GET":
                self._serve_events()
                return

            handler = server.routes.get(path)
            if handler is None:
                self._send_json(404, {"error": "Unknown endpoint"})
                return

            if method == "GET":
                if path not in routes.READ_ONLY:
                    self._send_json(405, {"error": "Method not allowed"})
                    return
                if path == "/api/settings":
                    handler = server.api.get_settings

            payload = self._read_json() if method == "POST" else {}
            try:
                status, body = handler(payload)
            except Exception as exc:  # noqa: BLE001 - never kill the server
                from core.errors import translate_error
                status, body = 500, {"error": translate_error(exc)}

            self._send_json(status, body)

        def do_GET(self):  # noqa: N802 - http.server API
            self._dispatch("GET")

        def do_POST(self):  # noqa: N802 - http.server API
            self._dispatch("POST")

    return Handler
