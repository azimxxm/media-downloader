"""Domain errors and user-facing error translation (Uzbek)."""


class DownloadCancelled(Exception):
    """Raised from the yt-dlp progress hook when the user cancels a job."""


class InvalidUrlError(ValueError):
    """URL did not match any supported platform."""


class FFmpegMissingError(RuntimeError):
    """FFmpeg is required for this operation but was not found."""


def translate_error(exception):
    """Convert a raw exception into a friendly Uzbek message."""
    if isinstance(exception, DownloadCancelled):
        return "Yuklab olish bekor qilindi."

    error_str = str(exception).lower()

    if "403" in error_str or "forbidden" in error_str:
        return "Video bloklangan yoki shaxsiy. Boshqa video tanlang."
    if "404" in error_str or "not found" in error_str:
        return "Video topilmadi. URL to'g'riligini tekshiring."
    if "network" in error_str or "connection" in error_str or "timeout" in error_str:
        return "Internet ulanishi bilan muammo. Ulanishni tekshiring."
    if "ffmpeg" in error_str:
        return "FFmpeg topilmadi. Iltimos, FFmpeg o'rnating:\nbrew install ffmpeg"
    if "login" in error_str or "rate-limit" in error_str or "cookies" in error_str:
        return "Instagram login talab qilmoqda. Keyinroq urinib ko'ring."
    if "private" in error_str:
        return "Bu video shaxsiy. Ommaviy videoni tanlang."
    if "copyright" in error_str or "blocked" in error_str:
        return "Video mualliflik huquqi sabab yuklab bo'lmaydi."
    if "age" in error_str or "restricted" in error_str:
        return "Bu video yoshga cheklangan."

    return f"Xatolik: {exception}"
