from core.media import build_quality_options, build_subtitle_options


def video(height, width=None, **extra):
    fmt = {"vcodec": "avc1.64", "acodec": "none", "height": height,
           "width": width if width is not None else int(height * 16 / 9)}
    fmt.update(extra)
    return fmt


def test_quality_options_are_sorted_high_to_low():
    info = {"formats": [video(360), video(1080), video(720)]}
    options = build_quality_options(info)

    assert options[0]["id"] == "best"
    assert [o["height"] for o in options[1:]] == [1080, 720, 360]


def test_quality_options_ignore_audio_only_formats():
    info = {"formats": [
        {"vcodec": "none", "acodec": "mp4a", "height": None},
        video(720),
    ]}
    options = build_quality_options(info)
    assert [o["height"] for o in options[1:]] == [720]


def test_quality_options_empty_without_video():
    assert build_quality_options({"formats": [{"vcodec": "none", "acodec": "mp4a"}]}) == []


def test_vertical_video_is_labelled_by_its_short_side():
    """A 1080x1920 Short is "1080p" to a viewer, even though height is 1920."""
    info = {"formats": [video(1920, width=1080), video(1280, width=720)]}
    options = build_quality_options(info)

    labels = [o["label"] for o in options[1:]]
    assert labels[0].startswith("1080p")
    assert labels[1].startswith("720p")

    # The selector still keys off height, which is what yt-dlp filters on.
    assert [o["id"] for o in options[1:]] == ["1920", "1280"]


def test_landscape_video_label_matches_height():
    options = build_quality_options({"formats": [video(1080)]})
    assert options[1]["label"].startswith("1080p")


def test_hdr_variants_are_flagged():
    info = {"formats": [
        video(2160, dynamic_range="HDR"),
        video(2160),
    ]}
    options = build_quality_options(info)
    assert options[1]["hdr"] is True
    assert "HDR" in options[1]["label"]


def test_largest_filesize_wins_per_resolution():
    info = {"formats": [
        video(1080, filesize=10 * 1024 * 1024),
        video(1080, filesize_approx=90 * 1024 * 1024),
    ]}
    options = build_quality_options(info)
    assert options[1]["filesize"] == 90 * 1024 * 1024
    assert "90.0 MB" in options[1]["label"]


def test_manual_subtitles_sort_before_automatic():
    info = {
        "subtitles": {"uz": [{}]},
        "automatic_captions": {"en": [{}], "uz": [{}]},
    }
    options = build_subtitle_options(info)
    codes = [o["code"] for o in options]

    assert set(codes) == {"uz", "en"}
    assert next(o for o in options if o["code"] == "uz")["auto"] is False
    assert next(o for o in options if o["code"] == "en")["auto"] is True
    assert options[0]["auto"] is False


def test_subtitle_list_is_capped():
    """YouTube offers 150+ auto-caption languages; the picker stays usable."""
    info = {"subtitles": {}, "automatic_captions": {f"l{i}": [{}] for i in range(200)}}
    assert len(build_subtitle_options(info)) == 40


def test_known_languages_get_readable_names():
    options = build_subtitle_options({"subtitles": {"uz": [{}]}, "automatic_captions": {}})
    assert options[0]["label"] == "O'zbekcha"
