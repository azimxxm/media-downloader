import pytest

from core.formatting import format_bytes, format_duration, format_eta, format_speed


@pytest.mark.parametrize("value,expected", [
    (0, "N/A"),
    (None, "N/A"),
    (512, "512.0 B"),
    (1024, "1.0 KB"),
    (1536, "1.5 KB"),
    (1024 ** 2, "1.0 MB"),
    (int(1.5 * 1024 ** 3), "1.5 GB"),
    (1024 ** 4, "1.0 TB"),
])
def test_format_bytes(value, expected):
    assert format_bytes(value) == expected


def test_format_speed_appends_unit():
    assert format_speed(1024 * 1024) == "1.0 MB/s"
    assert format_speed(0) == "N/A"


@pytest.mark.parametrize("seconds,expected", [
    (None, "N/A"),
    (-1, "N/A"),
    (0, "0:00"),
    (9, "0:09"),
    (65, "1:05"),
    (600, "10:00"),
    (3661, "1:01:01"),
])
def test_format_eta(seconds, expected):
    assert format_eta(seconds) == expected


def test_format_duration_blank_when_unknown():
    """An unknown duration renders as nothing rather than '0:00' or 'N/A'."""
    assert format_duration(0) == ""
    assert format_duration(None) == ""
    assert format_duration(125) == "2:05"
