#!/usr/bin/env python3
"""End-to-end smoke test for the native UI.

Drives the real pywebview window through the same bridge the shipped app uses:
bootstrap -> analyse -> download -> job completion. Needs a GUI session, so it
runs locally rather than in CI. The window stays hidden unless --visible is
passed, so the test never steals focus.

    .venv/bin/python packaging/ui_smoke.py [url] [--visible]
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import webview  # noqa: E402

from core import EventBus, JobManager  # noqa: E402
from core.appinfo import resource_path  # noqa: E402
from core.ffmpeg import extend_path  # noqa: E402
from server import Api, Bridge  # noqa: E402

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
VISIBLE = "--visible" in sys.argv

URL = ARGS[0] if ARGS else "https://www.youtube.com/shorts/lCVBzh1Nl88"

failures = []
manager = None      # JobManager, so the test can clean up what it downloaded


def check(label, condition, detail=""):
    mark = "\033[0;32m✓\033[0m" if condition else "\033[0;31m✗\033[0m"
    print(f"  {mark} {label}{f'  →  {detail}' if detail else ''}")
    if not condition:
        failures.append(label)


def js(window, expression):
    """Evaluate JS and decode the JSON payload it returns."""
    raw = window.evaluate_js(f"JSON.stringify({expression})")
    return json.loads(raw) if raw else None


def wait_for(window, expression, timeout=45, interval=0.4):
    """Poll a JS boolean expression until it turns true."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if js(window, f"!!({expression})"):
            return True
        time.sleep(interval)
    return False


def run(window):
    time.sleep(2.5)  # let the page settle and pywebview inject its bridge

    print("\n▸ Bootstrap")
    state = js(window, """({
        native: window.transport && window.transport.isNative,
        version: document.getElementById('version').textContent,
        dest: document.getElementById('titlebar-dest').textContent,
        modalHidden: document.getElementById('settings-modal').hidden,
        emptyVisible: !document.getElementById('empty-state').hidden
    })""")
    check("native transport", state["native"] is True)
    check("version rendered", bool(state["version"]), state["version"])
    check("destination rendered", state["dest"].startswith("~"), state["dest"])
    check("settings modal hidden", state["modalHidden"] is True)
    check("empty state visible", state["emptyVisible"] is True)

    print("\n▸ Analyze")
    window.evaluate_js(
        f"document.getElementById('url-input').value = {json.dumps(URL)};"
        "document.getElementById('url-input').dispatchEvent(new Event('input'));"
        "document.getElementById('analyze-btn').click();"
    )
    analysed = wait_for(window, "!document.getElementById('media-card').hidden")
    check("media card shown", analysed)

    if analysed:
        media = js(window, """({
            title: document.getElementById('media-title').textContent,
            chips: [...document.getElementById('media-chips').children].map(c => c.textContent),
            qualities: [...document.getElementById('quality-select').options].map(o => o.text),
            modes: [...document.getElementById('mode-group').children].map(b => b.textContent),
            hasThumb: !!document.querySelector('#media-thumb img'),
            accent: document.body.dataset.platform
        })""")
        check("title extracted", bool(media["title"]) and media["title"] != "—",
              media["title"][:48])
        check("thumbnail loaded (remote https from file://)", media["hasThumb"])
        check("quality options", len(media["qualities"]) > 1,
              " / ".join(media["qualities"][:4]))
        check("mode options", media["modes"] == ["Video", "Audio"],
              " / ".join(media["modes"]))
        check("platform accent applied", media["accent"] == "youtube", media["accent"])

        print("\n▸ Download")
        lowest = js(window, "[...document.getElementById('quality-select').options].pop().value")
        window.evaluate_js(
            f"document.getElementById('quality-select').value = {json.dumps(lowest)};"
        )
        window.evaluate_js("document.getElementById('download-btn').click();")

        appeared = wait_for(window, "document.querySelectorAll('#jobs-list .job').length > 0", 15)
        check("job row appeared", appeared)

        done = wait_for(
            window,
            "document.querySelector('#jobs-list .job[data-status=\\\"completed\\\"]')",
            120,
        )
        check("job completed", done)

        job = js(window, """(() => {
            const node = document.querySelector('#jobs-list .job');
            return node && {
                status: node.dataset.status,
                title: node.querySelector('.job-title').textContent,
                state: node.querySelector('.job-state').textContent,
                revealVisible: !node.querySelector('.job-reveal').hidden,
                width: node.querySelector('.progress-fill').style.width
            };
        })()""")
        if job:
            check("progress bar full", job["width"] == "100%", job["width"])
            check("reveal button offered", job["revealVisible"] is True)
            check("status label", job["state"] == "Tayyor", job["state"])

    print("\n▸ Responsive layout")
    for width, height in ((560, 700), (780, 900), (1100, 900)):
        window.resize(width, height)
        time.sleep(0.6)
        layout = js(window, """(() => {
            const doc = document.documentElement;
            const overflowing = [...document.querySelectorAll('body *')]
                .filter(n => n.getBoundingClientRect().right > doc.clientWidth + 1)
                .map(n => n.id || n.className || n.tagName)
                .slice(0, 4);
            const bar = document.querySelector('.titlebar').getBoundingClientRect();
            return {
                pageScrollsSideways: doc.scrollWidth > doc.clientWidth + 1,
                overflowing,
                titlebarFits: bar.width <= doc.clientWidth + 1,
                width: doc.clientWidth
            };
        })()""")
        check(
            f"{width}px - no horizontal overflow",
            not layout["pageScrollsSideways"] and not layout["overflowing"],
            ", ".join(layout["overflowing"]) if layout["overflowing"] else
            f"viewport {layout['width']}px",
        )
        check(f"{width}px - toolbar fits", layout["titlebarFits"])

    window.resize(780, 900)
    time.sleep(0.4)

    print("\n▸ Settings dialog")
    window.evaluate_js("document.getElementById('settings-btn').click();")
    time.sleep(0.4)
    check("modal opens", js(window, "!document.getElementById('settings-modal').hidden"))
    window.evaluate_js("document.getElementById('settings-close').click();")
    time.sleep(0.3)
    check("modal closes", js(window, "document.getElementById('settings-modal').hidden"))

    print("\n▸ Console")
    errors = js(window, "window.__mdlErrors || []")
    check("no uncaught JS errors", not errors, "; ".join(errors[:3]) if errors else "")

    print("\n▸ Cleanup")
    removed = 0
    for entry in manager.snapshot():
        path = entry.get("file_path")
        if path and Path(path).exists():
            Path(path).unlink()
            removed += 1
    check("downloaded test files removed", True, f"{removed} ta fayl")

    print()
    if failures:
        print(f"\033[0;31m{len(failures)} ta tekshiruv muvaffaqiyatsiz:\033[0m")
        for item in failures:
            print(f"   - {item}")
    else:
        print("\033[0;32mBarcha tekshiruvlar o'tdi.\033[0m")

    window.destroy()


def main():
    global manager

    extend_path()

    bus = EventBus()
    manager = JobManager(bus=bus, max_parallel=2)
    api = Api(manager)
    bridge = Bridge(api, bus)

    index = resource_path("web", "index.html")
    window = webview.create_window(
        "Media Downloader", index.as_uri(), js_api=bridge,
        width=780, height=900, background_color="#0e0e12",
        hidden=VISIBLE is False,
    )
    bridge.attach(window)

    window.events.loaded += lambda: window.evaluate_js(
        "window.__mdlErrors = [];"
        "window.addEventListener('error', e => window.__mdlErrors.push(String(e.message)));"
    )

    webview.start(run, window)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
