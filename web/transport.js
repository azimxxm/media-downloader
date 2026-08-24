/* Transport layer.

   The same UI runs in two places:
     file://  - packaged desktop app, talking to Python through the pywebview
                bridge (no socket, so macOS asks for no network permission)
     http://  - browser / development mode, talking to the local HTTP server

   Both expose one API: transport.call(path, body) and transport.onEvent(fn).  */

(() => {
  "use strict";

  const IS_NATIVE = location.protocol === "file:";
  const listeners = new Set();

  // Python pushes core events straight into this hook via evaluate_js.
  window.__mdlEvent = (payload) => {
    listeners.forEach((handler) => {
      try {
        handler(payload);
      } catch (error) {
        console.error("event handler failed", error);
      }
    });
  };

  /* ───────────────────────── native (pywebview) ───────────────────────── */

  function nativeReady() {
    if (window.pywebview?.api?.call) return Promise.resolve();
    return new Promise((resolve) => {
      window.addEventListener("pywebviewready", () => resolve(), { once: true });
    });
  }

  async function nativeCall(path, body) {
    const result = await window.pywebview.api.call(path, body ?? null);
    if (result && result.__error) throw new Error(result.__error);
    return result ?? {};
  }

  /* ───────────────────────── http (browser) ───────────────────────── */

  const TOKEN = document.body.dataset.token;

  async function httpCall(path, body) {
    const options = {
      method: body === undefined ? "GET" : "POST",
      headers: { "X-Auth-Token": TOKEN },
    };
    if (body !== undefined) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }

    const response = await fetch(path, options);
    let payload = {};
    try {
      payload = await response.json();
    } catch {
      payload = {};
    }
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    return payload;
  }

  function httpSubscribe() {
    const source = new EventSource(`/api/events?token=${encodeURIComponent(TOKEN)}`);

    source.onmessage = (event) => {
      try {
        window.__mdlEvent(JSON.parse(event.data));
      } catch {
        /* malformed frame - ignore */
      }
    };

    source.onerror = () => {
      source.close();
      setTimeout(httpSubscribe, 1500);   // machine slept, or server restarted
    };
  }

  /* ───────────────────────── public surface ───────────────────────── */

  const ready = IS_NATIVE
    ? nativeReady()
    : Promise.resolve(httpSubscribe());

  window.transport = {
    isNative: IS_NATIVE,
    ready: () => ready,
    call: (path, body) =>
      ready.then(() => (IS_NATIVE ? nativeCall(path, body) : httpCall(path, body))),
    onEvent: (handler) => listeners.add(handler),
  };
})();
