import pytest

from core.cache import metadata_cache
from core.events import EventBus
from core.jobs import JobManager
from server.api import Api


class RecordingManager(JobManager):
    """JobManager that records specs instead of downloading anything."""

    def __init__(self):
        super().__init__(bus=EventBus(), max_parallel=2)
        self.submitted = []

    def submit(self, spec):
        self.submitted.append(spec)
        return {"id": f"job{len(self.submitted)}", "url": spec["url"]}


@pytest.fixture
def api(monkeypatch):
    from core import ffmpeg as ffmpeg_utils

    monkeypatch.setattr(ffmpeg_utils, "check", lambda: (True, "ffmpeg 8.1", "/usr/bin/ffmpeg"))
    return Api(RecordingManager())


def test_bootstrap_reports_everything_the_ui_needs(api):
    status, payload = api.bootstrap()

    assert status == 200
    assert payload["ffmpeg"]["available"] is True
    assert "youtube_dir" in payload["settings"]
    assert payload["jobs"] == []
    assert payload["version"]


def test_analyze_rejects_an_unsupported_url(api):
    status, payload = api.analyze({"url": "https://vimeo.com/1"})
    assert status == 400
    assert "YouTube" in payload["error"]


def test_analyze_rejects_an_empty_url(api):
    status, _payload = api.analyze({"url": "   "})
    assert status == 400


def test_download_rejects_an_unsupported_url(api):
    status, _payload = api.download({"url": "https://vimeo.com/1", "mode": "video"})
    assert status == 400


def test_download_blocks_when_ffmpeg_is_missing(monkeypatch):
    from core import ffmpeg as ffmpeg_utils

    monkeypatch.setattr(ffmpeg_utils, "check", lambda: (False, "FFmpeg topilmadi", None))
    api = Api(RecordingManager())

    status, payload = api.download({"url": "https://youtu.be/x", "mode": "video"})
    assert status == 412
    assert "FFmpeg" in payload["error"]


def test_photo_download_does_not_require_ffmpeg(monkeypatch):
    """Images are fetched over plain HTTP, so a missing ffmpeg must not block them."""
    from core import ffmpeg as ffmpeg_utils

    monkeypatch.setattr(ffmpeg_utils, "check", lambda: (False, "FFmpeg topilmadi", None))
    api = Api(RecordingManager())

    status, _payload = api.download(
        {"url": "https://www.instagram.com/p/abc/", "mode": "photo"})
    assert status == 200


def test_download_routes_instagram_to_its_own_folder(api):
    api.download({"url": "https://www.instagram.com/reel/abc/", "mode": "video"})
    assert api.jobs.submitted[0]["outdir"].endswith("ig")


def test_download_routes_youtube_to_its_own_folder(api):
    api.download({"url": "https://youtu.be/abc", "mode": "video"})
    assert api.jobs.submitted[0]["outdir"].endswith("yt")


def test_download_falls_back_to_video_for_an_unknown_mode(api):
    api.download({"url": "https://youtu.be/abc", "mode": "wat"})
    assert api.jobs.submitted[0]["mode"] == "video"


def test_download_takes_media_info_from_the_server_cache(api):
    """The page never gets to dictate what gets written to disk."""
    url = "https://www.instagram.com/p/abc/"
    metadata_cache.set(url, {"title": "Trusted", "thumbnail": "https://cdn/t.jpg"})

    api.download({"url": url, "mode": "thumbnail",
                  "info": {"title": "Injected", "thumbnail": "https://evil/x.jpg"}})

    assert api.jobs.submitted[0]["info"]["title"] == "Trusted"


def test_batch_download_needs_items(api):
    status, payload = api.download_batch({"items": []})
    assert status == 400
    assert payload["error"]


def test_batch_download_skips_blank_urls(api):
    status, payload = api.download_batch({
        "mode": "audio",
        "outdir": "/tmp/out",
        "items": [{"url": "https://youtu.be/a"}, {"url": ""}, {"url": "https://youtu.be/b"}],
    })

    assert status == 200
    assert len(payload["jobs"]) == 2
    assert all(spec["mode"] == "audio" for spec in api.jobs.submitted)


def test_batch_download_rejects_an_all_blank_list(api):
    status, _payload = api.download_batch({"items": [{"url": ""}, {}]})
    assert status == 400


def test_settings_round_trip_and_apply_parallelism(api):
    status, payload = api.update_settings({"max_parallel": 4})

    assert status == 200
    assert payload["settings"]["max_parallel"] == 4
    assert api.jobs.max_parallel == 4


def test_settings_ignore_unknown_keys(api):
    _status, payload = api.update_settings({"evil": "value", "max_parallel": 3})
    assert "evil" not in payload["settings"]


def test_cancel_requires_a_job_id(api):
    status, _payload = api.cancel_job({})
    assert status == 400


def test_reveal_requires_a_path(api):
    status, _payload = api.reveal({})
    assert status == 400


def test_choose_folder_uses_the_injected_picker(api):
    api.folder_picker = lambda initial=None: "/Users/me/Movies"
    status, payload = api.choose_folder({"initial": "/Users/me"})

    assert status == 200
    assert payload["path"] == "/Users/me/Movies"


def test_choose_folder_survives_a_broken_picker(api, monkeypatch):
    from core import system

    monkeypatch.setattr(system, "choose_folder", lambda initial=None: None)
    api.folder_picker = lambda initial=None: (_ for _ in ()).throw(RuntimeError("boom"))

    status, payload = api.choose_folder({})
    assert status == 200
    assert payload["path"] is None
