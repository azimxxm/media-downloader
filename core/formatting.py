"""Human-readable formatting helpers. No UI framework imports."""


def format_bytes(value):
    """Convert a byte count to a short human string, e.g. '123.4 MB'."""
    if not value:
        return "N/A"

    size = float(value)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def format_speed(bytes_per_second):
    """Format a download speed, e.g. '2.1 MB/s'."""
    if not bytes_per_second:
        return "N/A"
    return f"{format_bytes(bytes_per_second)}/s"


def format_eta(seconds):
    """Format remaining seconds as m:ss (or h:mm:ss when long)."""
    if seconds is None:
        return "N/A"

    seconds = int(seconds)
    if seconds < 0:
        return "N/A"

    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)

    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_duration(seconds):
    """Format a media duration. Returns an empty string when unknown."""
    if not seconds:
        return ""
    return format_eta(seconds)
