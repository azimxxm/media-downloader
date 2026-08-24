"""URL validation and platform detection."""

import re

YOUTUBE = "youtube"
INSTAGRAM = "instagram"
UNKNOWN = "unknown"

_YOUTUBE_PATTERNS = (
    r"(https?://)?(www\.|m\.|music\.)?(youtube\.com|youtu\.be)",
    r"youtube\.com/watch\?v=",
    r"youtu\.be/",
    r"youtube\.com/playlist\?list=",
    r"youtube\.com/shorts/",
)

_INSTAGRAM_PATTERNS = (
    r"(https?://)?(www\.)?instagram\.com/(p|reel|reels|tv|stories)/",
    r"(https?://)?(www\.)?instagram\.com/[^/]+/(p|reel)/",
)

_PLAYLIST_PATTERN = r"[?&]list=([A-Za-z0-9_-]+)"


def detect_platform(url):
    """Return 'youtube', 'instagram' or 'unknown' for the given URL."""
    if not url:
        return UNKNOWN

    url = url.strip()
    if any(re.search(pattern, url, re.IGNORECASE) for pattern in _INSTAGRAM_PATTERNS):
        return INSTAGRAM
    if any(re.search(pattern, url, re.IGNORECASE) for pattern in _YOUTUBE_PATTERNS):
        return YOUTUBE
    return UNKNOWN


def is_playlist(url):
    """True when the URL points at a YouTube playlist."""
    if not url:
        return False
    return bool(re.search(_PLAYLIST_PATTERN, url))


def validate(url):
    """Validate a URL. Returns (is_valid, error_message_or_None)."""
    if not url or not url.strip():
        return False, "URL kiriting"

    platform = detect_platform(url)
    if platform == UNKNOWN:
        return False, "Faqat YouTube va Instagram havolalari qo'llab-quvvatlanadi."

    return True, None


def normalize_entry_url(raw, platform=YOUTUBE):
    """Playlist entries sometimes carry a bare video id — expand it to a full URL."""
    if not raw:
        return raw
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    if platform == YOUTUBE:
        return f"https://www.youtube.com/watch?v={raw}"
    return raw
