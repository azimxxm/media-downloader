"""Request handlers. Each returns (http_status, json_serialisable_payload)."""

import sys

from core import media, settings as settings_store
from core import ffmpeg as ffmpeg_utils
from core import system, urls as url_utils
from core.appinfo import APP_NAME, APP_VERSION
from core.cache import metadata_cache
from core.errors import translate_error

VALID_MODES = ("video", "audio", "photo", "thumbnail")


class Api:
    """Everything the web UI can ask the Python core to do."""

    def __init__(self, jobs):
        self.jobs = jobs
        # The desktop shell installs a native NSOpenPanel picker here. Without
        # it we fall back to osascript, which is what browser mode uses.
        self.folder_picker = None

    # ------------------------------------------------------------- lifecycle

    def bootstrap(self, _payload=None):
        """Everything the UI needs on first paint, in a single round trip."""
        available, message, path = ffmpeg_utils.check()
        current = settings_store.load()
        self.jobs.set_max_parallel(current["max_parallel"])

        return 200, {
            "app": APP_NAME,
            "version": APP_VERSION,
            "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "platform": sys.platform,
            "ffmpeg": {"available": available, "message": message, "path": path},
            "settings": current,
            "jobs": self.jobs.snapshot(),
        }

    def ffmpeg_status(self, _payload=None):
        ffmpeg_utils.reset_cache()
        available, message, path = ffmpeg_utils.check()
        return 200, {"available": available, "message": message, "path": path}

    # ---------------------------------------------------------------- media

    def analyze(self, payload):
        url = (payload or {}).get("url", "").strip()

        is_valid, error = url_utils.validate(url)
        if not is_valid:
            return 400, {"error": error}

        try:
            result = media.analyze(url)
        except ValueError as exc:
            return 400, {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001 - translated for the user
            return 502, {"error": translate_error(exc)}

        # Suggest the right destination folder for this platform.
        current = settings_store.load()
        key = "instagram_dir" if result["platform"] == url_utils.INSTAGRAM else "youtube_dir"
        result["suggested_dir"] = current[key]
        return 200, result

    # -------------------------------------------------------------- downloads

    def _build_spec(self, item, defaults):
        mode = item.get("mode") or defaults.get("mode") or "video"
        if mode not in VALID_MODES:
            mode = "video"

        url = (item.get("url") or "").strip()
        outdir = item.get("outdir") or defaults.get("outdir")
        if not outdir:
            platform = url_utils.detect_platform(url)
            current = settings_store.load()
            outdir = current["instagram_dir"] if platform == url_utils.INSTAGRAM \
                else current["youtube_dir"]

        return {
            "url": url,
            "mode": mode,
            "quality": item.get("quality") or defaults.get("quality") or "best",
            "outdir": outdir,
            "subtitles": bool(item.get("subtitles", defaults.get("subtitles"))),
            "subtitle_lang": item.get("subtitle_lang") or defaults.get("subtitle_lang") or "en",
            "title": item.get("title") or "",
            "thumbnail": item.get("thumbnail") or "",
            # Photo/thumbnail modes need the analysed metadata; use the server
            # side cache rather than trusting whatever the page sends back.
            "info": metadata_cache.get(url) or {},
        }

    def download(self, payload):
        payload = payload or {}
        url = (payload.get("url") or "").strip()

        is_valid, error = url_utils.validate(url)
        if not is_valid:
            return 400, {"error": error}

        mode = payload.get("mode", "video")
        if mode in ("video", "audio"):
            available, message, _path = ffmpeg_utils.check()
            if not available:
                return 412, {"error": message}

        spec = self._build_spec(payload, payload)
        job = self.jobs.submit(spec)
        return 200, {"job": job}

    def download_batch(self, payload):
        payload = payload or {}
        items = payload.get("items") or []
        if not items:
            return 400, {"error": "Hech qanday video tanlanmadi."}

        available, message, _path = ffmpeg_utils.check()
        if not available:
            return 412, {"error": message}

        specs = []
        for item in items:
            url = (item.get("url") or "").strip()
            if not url:
                continue
            specs.append(self._build_spec(item, payload))

        if not specs:
            return 400, {"error": "Yaroqli havola topilmadi."}

        return 200, {"jobs": self.jobs.submit_many(specs)}

    def list_jobs(self, _payload=None):
        return 200, {"jobs": self.jobs.snapshot()}

    def cancel_job(self, payload):
        job_id = (payload or {}).get("id")
        if not job_id:
            return 400, {"error": "Job id kerak."}
        return 200, {"cancelled": self.jobs.cancel(job_id)}

    def cancel_all(self, _payload=None):
        return 200, {"cancelled": self.jobs.cancel_all()}

    def clear_jobs(self, _payload=None):
        return 200, {"jobs": self.jobs.clear_finished()}

    # ------------------------------------------------------------ os actions

    def reveal(self, payload):
        path = (payload or {}).get("path")
        if not path:
            return 400, {"error": "Fayl yo'li kerak."}
        return 200, {"ok": system.reveal(path)}

    def open_folder(self, payload):
        path = (payload or {}).get("path") or settings_store.load()["youtube_dir"]
        return 200, {"ok": system.open_folder(path)}

    def clipboard(self, _payload=None):
        return 200, {"text": system.read_clipboard()}

    def choose_folder(self, payload):
        initial = (payload or {}).get("initial")
        picker = self.folder_picker or system.choose_folder
        try:
            picked = picker(initial)
        except Exception:  # noqa: BLE001 - a failed picker must not 500
            picked = system.choose_folder(initial)
        return 200, {"path": picked}

    # -------------------------------------------------------------- settings

    def get_settings(self, _payload=None):
        return 200, {"settings": settings_store.load()}

    def update_settings(self, payload):
        updated = settings_store.save(payload or {})
        self.jobs.set_max_parallel(updated["max_parallel"])
        return 200, {"settings": updated}
