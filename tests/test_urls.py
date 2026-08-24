import pytest

from core import urls


@pytest.mark.parametrize("url,expected", [
    ("https://www.youtube.com/watch?v=abc123", urls.YOUTUBE),
    ("https://youtu.be/abc123", urls.YOUTUBE),
    ("https://www.youtube.com/shorts/lCVBzh1Nl88", urls.YOUTUBE),
    ("https://m.youtube.com/watch?v=abc", urls.YOUTUBE),
    ("https://music.youtube.com/watch?v=abc", urls.YOUTUBE),
    ("youtube.com/playlist?list=PL123", urls.YOUTUBE),
    ("https://www.instagram.com/p/Cxyz/", urls.INSTAGRAM),
    ("https://instagram.com/reel/Cxyz/", urls.INSTAGRAM),
    ("https://www.instagram.com/stories/someone/123/", urls.INSTAGRAM),
    ("https://vimeo.com/12345", urls.UNKNOWN),
    ("not a url", urls.UNKNOWN),
    ("", urls.UNKNOWN),
    (None, urls.UNKNOWN),
])
def test_detect_platform(url, expected):
    assert urls.detect_platform(url) == expected


def test_instagram_wins_over_youtube_lookalikes():
    """An Instagram URL must never be classified as YouTube."""
    assert urls.detect_platform("https://instagram.com/p/youtube/") == urls.INSTAGRAM


@pytest.mark.parametrize("url,expected", [
    ("https://www.youtube.com/playlist?list=PL123", True),
    ("https://www.youtube.com/watch?v=abc&list=PL123", True),
    ("https://www.youtube.com/watch?v=abc", False),
    ("", False),
])
def test_is_playlist(url, expected):
    assert urls.is_playlist(url) is expected


def test_validate_rejects_empty():
    valid, message = urls.validate("")
    assert valid is False
    assert message


def test_validate_rejects_unsupported_platform():
    valid, message = urls.validate("https://vimeo.com/12345")
    assert valid is False
    assert "YouTube" in message


def test_validate_accepts_supported():
    assert urls.validate("https://youtu.be/abc") == (True, None)


def test_normalize_entry_url_expands_bare_ids():
    assert urls.normalize_entry_url("dQw4w9WgXcQ") == \
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_normalize_entry_url_leaves_full_urls_alone():
    full = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert urls.normalize_entry_url(full) == full
