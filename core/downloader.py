"""The download engine: yt-dlp options, progress plumbing, file resolution."""

import os
import urllib.request
from pathlib import Path

import yt_dlp

from .errors import DownloadCancelled
from .ffmpeg import ffmpeg_location
from .system import ensure_dir

# H.264 + AAC first so the result plays in QuickTime without re-encoding.
_MP4_PREFERRED = (
    "bestvideo[vcodec^=avc1][ext=mp4]+bestaudio[acodec^=mp4a][ext=m4a]"
    "/bestvideo[ext=mp4]+bestaudio[ext=m4a]"
    "/bestvideo+bestaudio"
    "/best[ext=mp4]/best"
)

_OUTPUT_TEMPLATE = "%(title).100B.%(ext)s"


def format_selector(mode, quality=None):
    """Build a yt-dlp format string for the requested mode and resolution."""
    if mode == "audio":
        return "bestaudio[acodec^=mp4a]/bestaudio/best"

    if mode == "photo":
        return "best[vcodec=none][acodec=none]/best"

    if not quality or quality == "best":
        return _MP4_PREFERRED

    height = str(quality)
    return (
        f"bestvideo[vcodec^=avc1][height<={height}][ext=mp4]+bestaudio[acodec^=mp4a][ext=m4a]"
        f"/bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]"
        f"/bestvideo[height<={height}]+bestaudio"
        f"/best[height<={height}]/best"
    )


def build_options(spec, hooks):
    """Assemble the yt-dlp option dict for one download."""
    outdir = ensure_dir(spec["outdir"])
    mode = spec.get("mode", "video")

    options = {
        "format": format_selector(mode, spec.get("quality")),
        "outtmpl": os.path.join(outdir, _OUTPUT_TEMPLATE),
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "progress_hooks": [hooks["progress"]],
        "postprocessor_hooks": [hooks["postprocessor"]],
        "retries": 5,
        "fragment_retries": 5,
        "continuedl": True,
    }

    location = ffmpeg_location()
    if location:
        options["ffmpeg_location"] = location

    if mode == "audio":
        # MP3 for maximum car-stereo compatibility, with title/artist tags and
        # cover art so offline players show something other than a filename.
        options["writethumbnail"] = True
        options["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            },
            {"key": "FFmpegMetadata", "add_metadata": True},
            {"key": "EmbedThumbnail", "already_have_thumbnail": False},
        ]
    elif mode == "video":
        options["merge_output_format"] = "mp4"
        options["postprocessors"] = [{"key": "FFmpegMetadata", "add_metadata": True}]

    if mode == "video" and spec.get("subtitles"):
        lang = spec.get("subtitle_lang") or "en"
        options.update({
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": [lang],
            "subtitlesformat": "srt/vtt/best",
            "postprocessors": list(options.get("postprocessors", [])) + [
                {"key": "FFmpegSubtitlesConvertor", "format": "srt"}
            ],
        })

    return options


def resolve_output_path(info, outdir, fallback_hint=None):
    """Find what yt-dlp actually wrote to disk."""
    requested = info.get("requested_downloads") or ()
    for item in requested:
        path = item.get("filepath")
        if path and os.path.exists(path):
            return path

    for key in ("filepath", "_filename"):
        path = info.get(key)
        if path and os.path.exists(path):
            return path

    # Post-processing renames the file (e.g. .webm -> .mp3), so fall back to
    # the newest file in the destination folder.
    if fallback_hint and os.path.exists(fallback_hint):
        return fallback_hint

    try:
        files = [f for f in Path(outdir).iterdir() if f.is_file() and not f.name.startswith(".")]
    except OSError:
        return None

    if not files:
        return None
    return str(max(files, key=lambda f: f.stat().st_mtime))


def _download_image(url, destination, on_progress):
    """Fetch a plain image (Instagram thumbnail / photo) with progress."""
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - https only
        total = int(response.headers.get("Content-Length") or 0)
        downloaded = 0

        with open(destination, "wb") as handle:
            while True:
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
                downloaded += len(chunk)
                on_progress({
                    "phase": "downloading",
                    "downloaded": downloaded,
                    "total": total,
                    "percent": (downloaded / total) if total else 0.0,
                    "speed": None,
                    "eta": None,
                })

    return destination


def _image_extension(url):
    lowered = (url or "").lower()
    for ext in ("png", "webp", "jpeg", "jpg"):
        if f".{ext}" in lowered:
            return "jpg" if ext == "jpeg" else ext
    return "jpg"


def _safe_stem(title, fallback="media"):
    """Filesystem-safe file stem derived from the media title."""
    cleaned = "".join(
        char for char in (title or "")[:60]
        if char.isalnum() or char in (" ", "-", "_", ".")
    ).strip()
    return cleaned or fallback


def download(spec, on_progress=None, cancel_event=None):
    """Run one download. Returns {'file_path', 'title'}.

    Raises DownloadCancelled when cancel_event is set mid-flight.
    """
    on_progress = on_progress or (lambda _payload: None)
    outdir = ensure_dir(spec["outdir"])
    mode = spec.get("mode", "video")
    url = spec["url"]

    def check_cancelled():
        if cancel_event is not None and cancel_event.is_set():
            raise DownloadCancelled()

    # A merged download fetches video then audio as separate files, each
    # reporting its own 0-100%. Aggregate them so the bar only moves forward.
    parts = {}
    highest = {"percent": 0.0}

    def progress_hook(data):
        check_cancelled()
        status = data.get("status")

        if status == "downloading":
            name = data.get("filename") or data.get("tmpfilename") or "part"
            parts[name] = {
                "downloaded": data.get("downloaded_bytes") or 0,
                "total": data.get("total_bytes") or data.get("total_bytes_estimate") or 0,
            }

            downloaded = sum(part["downloaded"] for part in parts.values())
            total = sum(part["total"] for part in parts.values())

            percent = (downloaded / total) if total else 0.0
            percent = min(max(percent, highest["percent"]), 0.999)
            highest["percent"] = percent

            on_progress({
                "phase": "downloading",
                "downloaded": downloaded,
                "total": total,
                "percent": percent,
                "speed": data.get("speed"),
                "eta": data.get("eta"),
            })
        elif status == "finished":
            # Subtitles land before the media, so their "finished" event would
            # flash the processing state before anything is really merging.
            name = (data.get("filename") or "").lower()
            if name.endswith((".srt", ".vtt", ".ass", ".ssa", ".lrc")):
                return
            on_progress({"phase": "processing", "percent": 1.0})

    def postprocessor_hook(data):
        check_cancelled()
        if data.get("status") == "started":
            on_progress({"phase": "processing", "percent": 1.0,
                         "note": data.get("postprocessor", "")})

    hooks = {"progress": progress_hook, "postprocessor": postprocessor_hook}

    # Thumbnail and photo-without-media go through a plain HTTP fetch.
    if mode == "thumbnail":
        info = spec.get("info") or {}
        thumbnail_url = info.get("thumbnail") or ""
        if not thumbnail_url:
            raise RuntimeError("Bu media uchun rasm (thumbnail) mavjud emas.")

        stem = _safe_stem(info.get("title"), "instagram_media")
        destination = os.path.join(
            outdir, f"{stem}_thumbnail.{_image_extension(thumbnail_url)}"
        )
        check_cancelled()
        _download_image(thumbnail_url, destination, on_progress)
        return {"file_path": destination, "title": info.get("title") or stem}

    if mode == "photo":
        info = spec.get("info") or {}
        has_photo = info.get("has_image")
        if has_photo is None:
            has_photo = any(
                f.get("vcodec") in (None, "none") and f.get("acodec") in (None, "none")
                for f in (info.get("formats") or ())
            )

        if not has_photo:
            thumbnail_url = info.get("thumbnail") or ""
            if not thumbnail_url:
                raise RuntimeError(
                    "Bu postda rasm yo'q. Video yoki Thumbnail variantini tanlang."
                )
            stem = _safe_stem(info.get("title"), "instagram_media")
            destination = os.path.join(
                outdir, f"{stem}_photo.{_image_extension(thumbnail_url)}"
            )
            check_cancelled()
            _download_image(thumbnail_url, destination, on_progress)
            return {"file_path": destination, "title": info.get("title") or stem}

    options = build_options(spec, hooks)
    check_cancelled()

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)

    if info is None:
        raise RuntimeError("yt-dlp media haqida ma'lumot qaytarmadi.")

    file_path = resolve_output_path(info, outdir)
    return {"file_path": file_path, "title": info.get("title") or spec.get("title") or ""}
