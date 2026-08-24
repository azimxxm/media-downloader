import threading
import time

import pytest

from core import jobs as jobs_module
from core.errors import DownloadCancelled
from core.events import EventBus
from core.jobs import JobManager


def wait_until(predicate, timeout=5.0, interval=0.02):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


@pytest.fixture
def manager():
    return JobManager(bus=EventBus(), max_parallel=2)


def spec(url="https://youtu.be/x", **extra):
    payload = {"url": url, "mode": "video", "outdir": "/tmp", "title": "Test"}
    payload.update(extra)
    return payload


def test_successful_job_reaches_completed(manager, monkeypatch):
    monkeypatch.setattr(jobs_module, "download",
                        lambda s, on_progress=None, cancel_event=None:
                        {"file_path": "/tmp/out.mp4", "title": "Real Title"})

    job = manager.submit(spec())
    assert wait_until(lambda: manager.snapshot()[0]["status"] == "completed")

    result = manager.snapshot()[0]
    assert result["id"] == job["id"]
    assert result["percent"] == 1.0
    assert result["file_path"] == "/tmp/out.mp4"
    assert result["title"] == "Real Title"       # yt-dlp's title replaces the hint
    assert result["error"] is None


def test_failure_is_translated_for_the_user(manager, monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("HTTP Error 403: Forbidden")

    monkeypatch.setattr(jobs_module, "download", boom)
    manager.submit(spec())

    assert wait_until(lambda: manager.snapshot()[0]["status"] == "error")
    assert "bloklangan" in manager.snapshot()[0]["error"]


def test_cancel_marks_the_job_cancelled(manager, monkeypatch):
    started = threading.Event()

    def slow(_spec, on_progress=None, cancel_event=None):
        started.set()
        for _ in range(200):
            if cancel_event.is_set():
                raise DownloadCancelled()
            time.sleep(0.01)
        return {"file_path": "/tmp/out.mp4", "title": "x"}

    monkeypatch.setattr(jobs_module, "download", slow)
    job = manager.submit(spec())

    assert started.wait(3)
    assert manager.cancel(job["id"]) is True
    assert wait_until(lambda: manager.snapshot()[0]["status"] == "cancelled")


def test_cancel_is_rejected_once_finished(manager, monkeypatch):
    monkeypatch.setattr(jobs_module, "download",
                        lambda *a, **k: {"file_path": "/tmp/o.mp4", "title": "x"})
    job = manager.submit(spec())

    assert wait_until(lambda: manager.snapshot()[0]["status"] == "completed")
    assert manager.cancel(job["id"]) is False


def test_cancel_of_unknown_job_is_harmless(manager):
    assert manager.cancel("does-not-exist") is False


def test_parallel_limit_is_respected(monkeypatch):
    manager = JobManager(bus=EventBus(), max_parallel=2)

    live = 0
    peak = 0
    lock = threading.Lock()
    release = threading.Event()

    def blocking(*_args, **_kwargs):
        nonlocal live, peak
        with lock:
            live += 1
            peak = max(peak, live)
        release.wait(5)
        with lock:
            live -= 1
        return {"file_path": "/tmp/o.mp4", "title": "x"}

    monkeypatch.setattr(jobs_module, "download", blocking)
    for index in range(6):
        manager.submit(spec(url=f"https://youtu.be/{index}"))

    assert wait_until(lambda: peak >= 2)
    time.sleep(0.3)                    # give any extra worker a chance to slip through
    assert peak == 2

    release.set()
    assert wait_until(
        lambda: all(j["status"] == "completed" for j in manager.snapshot()), timeout=10)


def test_progress_updates_flow_through_the_bus(manager, monkeypatch):
    def reporting(_spec, on_progress=None, cancel_event=None):
        on_progress({"phase": "downloading", "percent": 0.5,
                     "downloaded": 50, "total": 100, "speed": 1024, "eta": 3})
        on_progress({"phase": "processing", "percent": 1.0})
        return {"file_path": "/tmp/o.mp4", "title": "x"}

    listener = manager.bus.subscribe()
    monkeypatch.setattr(jobs_module, "download", reporting)
    manager.submit(spec())

    assert wait_until(lambda: manager.snapshot()[0]["status"] == "completed")

    seen = []
    while not listener.empty():
        seen.append(listener.get_nowait())

    statuses = [e["job"]["status"] for e in seen if e.get("type") == "job"]
    assert "running" in statuses
    assert "processing" in statuses
    assert statuses[-1] == "completed"


def test_snapshot_preserves_submission_order(manager, monkeypatch):
    monkeypatch.setattr(jobs_module, "download",
                        lambda *a, **k: {"file_path": "/tmp/o.mp4", "title": "x"})

    submitted = [manager.submit(spec(url=f"https://youtu.be/{i}"))["id"] for i in range(4)]
    assert [j["id"] for j in manager.snapshot()] == submitted


def test_clear_finished_keeps_running_jobs(manager, monkeypatch):
    release = threading.Event()

    def maybe_slow(job_spec, on_progress=None, cancel_event=None):
        if job_spec["url"].endswith("slow"):
            release.wait(5)
        return {"file_path": "/tmp/o.mp4", "title": "x"}

    monkeypatch.setattr(jobs_module, "download", maybe_slow)
    manager.submit(spec(url="https://youtu.be/fast"))
    slow = manager.submit(spec(url="https://youtu.be/slow"))

    assert wait_until(
        lambda: any(j["status"] == "completed" for j in manager.snapshot()))

    remaining = manager.clear_finished()
    assert [j["id"] for j in remaining] == [slow["id"]]

    release.set()


def test_max_parallel_is_clamped(manager):
    assert manager.set_max_parallel(99) == 8
    assert manager.set_max_parallel(0) == 1
