# CLAUDE.md

Guidance for Claude Code (claude.ai/code) when working in this repository.

## Project Overview

Media Downloader is a macOS desktop app for downloading YouTube and Instagram
media (video, MP3 audio, images, subtitles) for offline use. The UI is plain
HTML/CSS/JS rendered in a native WKWebView; all logic is Python on top of
yt-dlp and FFmpeg.

It was previously written in Flet. That was replaced because Flet bundles a
full Flutter engine and `flet pack` produced unreliable macOS `.app` bundles.
Do not reintroduce Flet or any other Python GUI framework.

## Architecture

Four layers, each unaware of the one above it:

```
web/          HTML + CSS + vanilla JS. No build step, no npm, no bundler.
   │ transport.js picks a transport at runtime by location.protocol
   ├── file:  → server/bridge.py      pywebview js_api   (packaged app)
   └── http:  → server/http_server.py stdlib HTTP + SSE  (browser / dev)
                        │ server/routes.py — one API contract for both
core/         Pure Python. Imports no UI framework at all.
```

### Non-negotiable constraints

These exist for specific reasons; changing them reintroduces solved bugs.

1. **`core/` must never import a UI framework.** It is driven by the HTTP
   server, the native bridge, and the tests without modification.

2. **The packaged app must not open a listening socket.** macOS 15+ shows a
   *"find devices on your local network"* permission prompt for any listening
   TCP port, even on 127.0.0.1. `Bridge` avoids this by using pywebview's
   `js_api` channel. The window URL must stay `file://` — pywebview starts its
   own HTTP server for relative paths.

3. **HTTP mode uses the standard library only.** No FastAPI, uvicorn, or
   websockets: they cause PyInstaller hidden-import failures, which is the
   class of problem this rewrite exists to escape.

4. **`_LoopbackHTTPServer` must keep overriding `server_bind`.** The stock
   `http.server` calls `socket.getfqdn()` there, which does a reverse DNS
   lookup through mDNSResponder.

5. **The CSP in `index.html` needs `'unsafe-eval'`.** pywebview delivers
   Python → JS events by evaluating a string; without it every progress update
   is silently dropped. All media text is rendered via `textContent`, never
   `innerHTML`, which is what actually prevents injection here.

6. **`[hidden] { display: none !important; }` must stay in `styles.css`.** The
   whole UI toggles visibility through the `hidden` attribute, and any explicit
   `display` rule beats the user-agent default.

7. **Format selectors use `vcodec^=avc1`, not `vcodec=h264`.** yt-dlp compares
   the raw codec string (`avc1.640028`), so `=h264` never matches and silently
   falls back to a low-resolution progressive format.

8. **Download progress is aggregated across parts.** A merged download fetches
   video then audio, each reporting its own 0–100%. `core/downloader.py` sums
   them and clamps the result monotonically.

## Commands

```bash
# Setup
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt

# Run
.venv/bin/python app.py                  # native window
.venv/bin/python app.py --browser        # browser mode (fast UI iteration)
.venv/bin/python app.py --hidden         # native, no visible window

# Test
.venv/bin/python -m pytest tests/ -q     # unit tests, no network
.venv/bin/python packaging/ui_smoke.py   # UI end-to-end in a hidden window

# Build
./packaging/build_macos.sh               # .app → ad-hoc signature → .dmg
.venv/bin/python packaging/make_icon.py  # regenerate assets/icon.{png,icns}
```

`packaging/ui_smoke.py` drives the real pywebview window through the shipping
bridge: bootstrap → analyse → download → completion, plus responsive checks at
560/780/1100px. Run it after any change to `web/` or `server/`.

## Conventions

- UI strings and user-facing error messages are in Uzbek. Code, identifiers,
  comments, and commit messages are in English.
- `core/errors.py::translate_error` is the single place raw exceptions become
  user-facing text.
- New API endpoints go in `server/routes.py` so both transports get them.
- The build script's smoke test must keep passing; it is the last gate before
  a `.dmg` is produced.

## Release

Tagging `v*` triggers `.github/workflows/release.yml`, which builds arm64 and
x86_64 `.dmg` files and attaches them to a GitHub Release.

Builds are ad-hoc signed, not notarized, so first launch requires
*System Settings ▸ Privacy & Security ▸ Open Anyway*. Setting `SIGN_IDENTITY`
to a Developer ID enables a real signature.
