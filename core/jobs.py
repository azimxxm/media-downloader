"""Job queue: runs downloads on background threads and streams progress."""

import threading
import time
import uuid

from .downloader import download
from .errors import DownloadCancelled, translate_error
from .events import EventBus
from .formatting import format_bytes, format_eta, format_speed

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_PROCESSING = "processing"
STATUS_COMPLETED = "completed"
STATUS_ERROR = "error"
STATUS_CANCELLED = "cancelled"

_PROGRESS_INTERVAL = 0.12  # seconds between progress broadcasts per job


class Job:
    """One download, plus everything the UI needs to render its row."""

    def __init__(self, spec):
        self.id = uuid.uuid4().hex[:12]
        self.spec = spec
        self.url = spec.get("url", "")
        self.title = spec.get("title") or spec.get("url", "")
        self.mode = spec.get("mode", "video")
        self.quality = spec.get("quality") or "best"
        self.thumbnail = spec.get("thumbnail") or ""
        self.outdir = spec.get("outdir", "")

        self.status = STATUS_QUEUED
        self.percent = 0.0
        self.downloaded = 0
        self.total = 0
        self.speed = None
        self.eta = None
        self.file_path = None
        self.error = None
        self.created_at = time.time()

        self.cancel_event = threading.Event()
        self._last_emit = 0.0

    def to_dict(self):
        return {
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "mode": self.mode,
            "quality": self.quality,
            "thumbnail": self.thumbnail,
            "status": self.status,
            "percent": round(self.percent, 4),
            "downloaded": self.downloaded,
            "total": self.total,
            "size_text": format_bytes(self.total) if self.total else "",
            "speed_text": format_speed(self.speed) if self.speed else "",
            "eta_text": format_eta(self.eta) if self.eta is not None else "",
            "file_path": self.file_path,
            "error": self.error,
            "created_at": self.created_at,
        }


class JobManager:
    """Runs at most `max_parallel` downloads at once and publishes updates."""

    def __init__(self, bus=None, max_parallel=2):
        self.bus = bus or EventBus()
        self._jobs = {}
        self._order = []
        self._lock = threading.Lock()
        self._slots = threading.Semaphore(max_parallel)
        self._max_parallel = max_parallel

    # ---------------------------------------------------------------- public

    def submit(self, spec):
        """Queue one download and return its job dict."""
        job = Job(spec)

        with self._lock:
            self._jobs[job.id] = job
            self._order.append(job.id)

        self._emit(job)
        threading.Thread(target=self._run, args=(job,), daemon=True).start()
        return job.to_dict()

    def submit_many(self, specs):
        return [self.submit(spec) for spec in specs]

    def cancel(self, job_id):
        job = self._jobs.get(job_id)
        if not job:
            return False

        if job.status in (STATUS_COMPLETED, STATUS_ERROR, STATUS_CANCELLED):
            return False

        job.cancel_event.set()
        return True

    def cancel_all(self):
        cancelled = 0
        for job in list(self._jobs.values()):
            if self.cancel(job.id):
                cancelled += 1
        return cancelled

    def clear_finished(self):
        """Drop completed/failed jobs from the list."""
        with self._lock:
            keep = []
            for job_id in self._order:
                job = self._jobs[job_id]
                if job.status in (STATUS_COMPLETED, STATUS_ERROR, STATUS_CANCELLED):
                    del self._jobs[job_id]
                else:
                    keep.append(job_id)
            self._order = keep

        self.bus.publish({"type": "jobs_cleared"})
        return self.snapshot()

    def snapshot(self):
        with self._lock:
            return [self._jobs[job_id].to_dict() for job_id in self._order]

    def set_max_parallel(self, value):
        """Adjust concurrency by handing out (or reclaiming) semaphore slots."""
        value = max(1, min(8, int(value)))
        with self._lock:
            delta = value - self._max_parallel
            self._max_parallel = value

        if delta > 0:
            for _ in range(delta):
                self._slots.release()
        elif delta < 0:
            # Reclaim lazily so we never block the caller.
            threading.Thread(
                target=self._reclaim_slots, args=(-delta,), daemon=True
            ).start()

        return value

    @property
    def max_parallel(self):
        return self._max_parallel

    # --------------------------------------------------------------- internal

    def _reclaim_slots(self, count):
        for _ in range(count):
            self._slots.acquire()

    def _emit(self, job):
        self.bus.publish({"type": "job", "job": job.to_dict()})

    def _emit_throttled(self, job):
        now = time.monotonic()
        if now - job._last_emit < _PROGRESS_INTERVAL:
            return
        job._last_emit = now
        self._emit(job)

    def _acquire_slot(self, job):
        """Wait for a free slot, staying responsive to cancellation."""
        while not self._slots.acquire(timeout=0.25):
            if job.cancel_event.is_set():
                return False
        return True

    def _run(self, job):
        if not self._acquire_slot(job):
            job.status = STATUS_CANCELLED
            self._emit(job)
            return

        try:
            job.status = STATUS_RUNNING
            self._emit(job)

            def on_progress(payload):
                phase = payload.get("phase")
                if phase == "processing":
                    job.status = STATUS_PROCESSING
                    job.percent = 1.0
                    job.speed = None
                    job.eta = None
                    self._emit(job)
                    return

                job.status = STATUS_RUNNING
                job.percent = payload.get("percent") or 0.0
                job.downloaded = payload.get("downloaded") or 0
                job.total = payload.get("total") or 0
                job.speed = payload.get("speed")
                job.eta = payload.get("eta")
                self._emit_throttled(job)

            result = download(job.spec, on_progress=on_progress,
                              cancel_event=job.cancel_event)

            job.file_path = result.get("file_path")
            if result.get("title"):
                job.title = result["title"]
            job.status = STATUS_COMPLETED
            job.percent = 1.0
            job.speed = None
            job.eta = None

        except DownloadCancelled:
            job.status = STATUS_CANCELLED
            job.error = "Bekor qilindi"
        except Exception as exc:  # noqa: BLE001 - surfaced to the user verbatim
            if job.cancel_event.is_set():
                job.status = STATUS_CANCELLED
                job.error = "Bekor qilindi"
            else:
                job.status = STATUS_ERROR
                job.error = translate_error(exc)
        finally:
            self._slots.release()
            self._emit(job)
