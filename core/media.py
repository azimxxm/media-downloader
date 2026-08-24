"""Metadata extraction: turns a URL into everything the UI needs to show."""

import yt_dlp

from . import urls as url_utils
from .cache import metadata_cache
from .ffmpeg import ffmpeg_location
from .formatting import format_bytes, format_duration

LANGUAGE_NAMES = {
    "en": "English", "uz": "O'zbekcha", "ru": "Русский", "tr": "Türkçe",
    "es": "Español", "fr": "Français", "de": "Deutsch", "ar": "العربية",
    "hi": "हिन्दी", "ja": "日本語", "ko": "한국어", "zh": "中文",
}


def _base_options(**extra):
    """yt-dlp options shared by every metadata call."""
    options = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "ignoreerrors": False,
    }
    location = ffmpeg_location()
    if location:
        options["ffmpeg_location"] = location
    options.update(extra)
    return options


def _largest_filesize(formats):
    """Biggest known size across formats - a rough 'how big is this' hint."""
    largest = 0
    for fmt in formats or ():
        size = fmt.get("filesize") or fmt.get("filesize_approx") or 0
        if size > largest:
            largest = size
    return largest


def _display_resolution(fmt):
    """Resolution as a viewer would name it.

    yt-dlp filters on height, but a 1080x1920 Short is "1080p" to everyone
    except the format selector - so label by the short side.
    """
    height = fmt.get("height") or 0
    width = fmt.get("width") or 0
    if width and height and width < height:
        return width
    return height


def build_quality_options(info):
    """Collapse yt-dlp's format list into one entry per resolution."""
    by_height = {}
    for fmt in info.get("formats") or ():
        if fmt.get("vcodec") in (None, "none"):
            continue
        height = fmt.get("height")
        if not height:
            continue
        by_height.setdefault(height, []).append(fmt)

    options = []
    for height in sorted(by_height, reverse=True):
        variants = by_height[height]
        is_hdr = any("hdr" in (f.get("dynamic_range") or "").lower() for f in variants)
        size = _largest_filesize(variants)
        shown = max((_display_resolution(f) for f in variants), default=height)

        label = f"{shown}p"
        if is_hdr:
            label += " HDR"
        if size:
            label += f" · {format_bytes(size)}"

        options.append({
            "id": str(height),
            "label": label,
            "height": height,
            "hdr": is_hdr,
            "filesize": size,
        })

    if options:
        options.insert(0, {
            "id": "best",
            "label": "Eng yaxshi sifat",
            "height": 10000,
            "hdr": False,
            "filesize": 0,
        })

    return options


def build_subtitle_options(info):
    """Available subtitle tracks (manual first, then auto-generated)."""
    seen = {}

    for code in (info.get("subtitles") or {}):
        seen[code] = {"code": code, "label": LANGUAGE_NAMES.get(code, code), "auto": False}

    for code in (info.get("automatic_captions") or {}):
        if code in seen:
            continue
        label = LANGUAGE_NAMES.get(code, code)
        seen[code] = {"code": code, "label": f"{label} (avto)", "auto": True}

    ordered = sorted(seen.values(), key=lambda item: (item["auto"], item["label"]))
    return ordered[:40]  # the auto-caption list can run to 150+ languages


def _entry_to_item(index, entry, platform):
    """Normalise one playlist entry."""
    duration = int(entry.get("duration") or 0)
    raw_url = entry.get("url") or entry.get("webpage_url") or entry.get("id") or ""
    return {
        "index": index,
        "id": entry.get("id") or str(index),
        "url": url_utils.normalize_entry_url(raw_url, platform),
        "title": entry.get("title") or "Unknown",
        "duration": duration,
        "duration_text": format_duration(duration),
        "thumbnail": entry.get("thumbnail") or "",
    }


def analyze_playlist(url):
    """Flat playlist listing - fast, one request, no per-video metadata."""
    options = _base_options(extract_flat="in_playlist")
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)

    entries = []
    for index, entry in enumerate(info.get("entries") or ()):
        if entry:
            entries.append(_entry_to_item(index, entry, url_utils.YOUTUBE))

    return {
        "platform": url_utils.YOUTUBE,
        "kind": "playlist",
        "url": url,
        "webpage_url": info.get("webpage_url") or url,
        "title": info.get("title") or "Playlist",
        "uploader": info.get("uploader") or info.get("channel") or "",
        "thumbnail": info.get("thumbnail") or (entries[0]["thumbnail"] if entries else ""),
        "count": len(entries),
        "entries": entries,
    }


def analyze_single(url, use_cache=True):
    """Full metadata for one video / reel / photo post."""
    if use_cache:
        cached = metadata_cache.get(url)
        if cached:
            return cached

    with yt_dlp.YoutubeDL(_base_options()) as ydl:
        info = ydl.extract_info(url, download=False)

    formats = info.get("formats") or ()
    has_video = any(f.get("vcodec") not in (None, "none") for f in formats)
    has_audio = any(f.get("acodec") not in (None, "none") for f in formats)
    has_image = any(
        f.get("vcodec") in (None, "none") and f.get("acodec") in (None, "none")
        for f in formats
    )

    platform = url_utils.detect_platform(url)
    duration = int(info.get("duration") or 0)
    filesize = _largest_filesize(formats)

    title = info.get("title") or info.get("description") or "Media"
    if len(title) > 140:
        title = title[:140].rstrip() + "…"

    result = {
        "platform": platform,
        "kind": "video" if has_video else ("audio" if has_audio else "image"),
        "url": url,
        "webpage_url": info.get("webpage_url") or url,
        "title": title,
        "uploader": info.get("uploader") or info.get("channel") or info.get("uploader_id") or "",
        "thumbnail": info.get("thumbnail") or "",
        "duration": duration,
        "duration_text": format_duration(duration),
        "view_count": info.get("view_count") or 0,
        "filesize": filesize,
        "filesize_text": format_bytes(filesize) if filesize else "",
        "has_video": has_video,
        "has_audio": has_audio,
        "has_image": has_image,
        "qualities": build_quality_options(info) if has_video else [],
        "subtitles": build_subtitle_options(info) if platform == url_utils.YOUTUBE else [],
        "entries": [],
        "count": 1,
    }

    metadata_cache.set(url, result)
    return result


def analyze(url):
    """Entry point used by the API. Picks playlist vs single automatically."""
    url = (url or "").strip()
    is_valid, error = url_utils.validate(url)
    if not is_valid:
        raise ValueError(error)

    if url_utils.is_playlist(url):
        return analyze_playlist(url)
    return analyze_single(url)
