import os

import pytest

from core import downloader


def test_audio_selector_prefers_aac_then_anything():
    selector = downloader.format_selector("audio")
    assert selector.startswith("bestaudio[acodec^=mp4a]")
    assert selector.endswith("/best")


def test_photo_selector_excludes_video_and_audio_streams():
    assert downloader.format_selector("photo").startswith("best[vcodec=none][acodec=none]")


def test_best_video_selector_prefers_h264_and_aac():
    """QuickTime plays h264+aac without a re-encode, so ask for it first."""
    selector = downloader.format_selector("video", "best")
    assert selector.startswith("bestvideo[vcodec^=avc1][ext=mp4]+bestaudio[acodec^=mp4a][ext=m4a]")


def test_video_selector_uses_codec_prefix_not_equality():
    """vcodec is a string like 'avc1.640028', so '=h264' would never match."""
    selector = downloader.format_selector("video", "1080")
    assert "vcodec^=avc1" in selector
    assert "vcodec=h264" not in selector


def test_quality_selector_caps_rather_than_pins_height():
    """height<= keeps a video downloadable when the exact rung is missing."""
    selector = downloader.format_selector("video", "720")
    assert "[height<=720]" in selector
    assert "[height=720]" not in selector


def test_quality_selector_always_has_a_fallback():
    assert downloader.format_selector("video", "4320").endswith("/best")


@pytest.mark.parametrize("url,expected", [
    ("https://cdn/pic.jpg?x=1", "jpg"),
    ("https://cdn/pic.jpeg", "jpg"),
    ("https://cdn/pic.PNG", "png"),
    ("https://cdn/pic.webp", "webp"),
    ("https://cdn/no-extension", "jpg"),
    ("", "jpg"),
])
def test_image_extension(url, expected):
    assert downloader._image_extension(url) == expected


def test_safe_stem_strips_filesystem_hostile_characters():
    assert downloader._safe_stem("a/b:c*d?") == "abcd"


def test_safe_stem_falls_back_when_nothing_survives():
    assert downloader._safe_stem("///") == "media"
    assert downloader._safe_stem("") == "media"


def test_safe_stem_is_length_bounded():
    assert len(downloader._safe_stem("x" * 500)) <= 60


def test_resolve_output_path_prefers_requested_downloads(tmp_path):
    real = tmp_path / "video.mp4"
    real.write_bytes(b"data")

    info = {"requested_downloads": [{"filepath": str(real)}]}
    assert downloader.resolve_output_path(info, str(tmp_path)) == str(real)


def test_resolve_output_path_skips_paths_that_no_longer_exist(tmp_path):
    """Post-processing renames files, so a stale path must not be returned."""
    converted = tmp_path / "audio.mp3"
    converted.write_bytes(b"data")

    info = {"requested_downloads": [{"filepath": str(tmp_path / "audio.webm")}]}
    assert downloader.resolve_output_path(info, str(tmp_path)) == str(converted)


def test_resolve_output_path_returns_newest_file(tmp_path):
    old = tmp_path / "old.mp4"
    old.write_bytes(b"1")
    os.utime(old, (1, 1))

    new = tmp_path / "new.mp4"
    new.write_bytes(b"2")

    assert downloader.resolve_output_path({}, str(tmp_path)) == str(new)


def test_resolve_output_path_ignores_dotfiles(tmp_path):
    (tmp_path / ".DS_Store").write_bytes(b"junk")
    assert downloader.resolve_output_path({}, str(tmp_path)) is None


def test_build_options_audio_embeds_metadata_and_cover(tmp_path):
    hooks = {"progress": lambda d: None, "postprocessor": lambda d: None}
    options = build = downloader.build_options(
        {"url": "u", "mode": "audio", "outdir": str(tmp_path)}, hooks)

    keys = [pp["key"] for pp in options["postprocessors"]]
    assert keys == ["FFmpegExtractAudio", "FFmpegMetadata", "EmbedThumbnail"]
    assert options["writethumbnail"] is True
    assert build["format"].startswith("bestaudio")


def test_build_options_video_merges_to_mp4(tmp_path):
    hooks = {"progress": lambda d: None, "postprocessor": lambda d: None}
    options = downloader.build_options(
        {"url": "u", "mode": "video", "outdir": str(tmp_path)}, hooks)

    assert options["merge_output_format"] == "mp4"
    assert options["noplaylist"] is True


def test_build_options_subtitles_keep_the_mode_postprocessors(tmp_path):
    hooks = {"progress": lambda d: None, "postprocessor": lambda d: None}
    options = downloader.build_options(
        {"url": "u", "mode": "video", "outdir": str(tmp_path),
         "subtitles": True, "subtitle_lang": "uz"},
        hooks)

    keys = [pp["key"] for pp in options["postprocessors"]]
    assert "FFmpegMetadata" in keys
    assert "FFmpegSubtitlesConvertor" in keys
    assert options["subtitleslangs"] == ["uz"]


def test_build_options_creates_the_destination(tmp_path):
    target = tmp_path / "nested" / "folder"
    hooks = {"progress": lambda d: None, "postprocessor": lambda d: None}

    downloader.build_options({"url": "u", "mode": "video", "outdir": str(target)}, hooks)
    assert target.is_dir()
