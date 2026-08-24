"""One route table, shared by both transports.

The HTTP server and the native pywebview bridge expose exactly the same API,
so the web UI is written once and does not care which one it is talking to.
"""

#: Endpoints that are safe to reach with a plain GET.
READ_ONLY = frozenset({
    "/api/bootstrap",
    "/api/jobs",
    "/api/clipboard",
    "/api/settings",
    "/api/ffmpeg",
})


def build(api):
    """Map request paths to Api methods."""
    return {
        "/api/bootstrap": api.bootstrap,
        "/api/jobs": api.list_jobs,
        "/api/clipboard": api.clipboard,
        "/api/ffmpeg": api.ffmpeg_status,
        "/api/analyze": api.analyze,
        "/api/download": api.download,
        "/api/download/batch": api.download_batch,
        "/api/jobs/cancel": api.cancel_job,
        "/api/jobs/cancel-all": api.cancel_all,
        "/api/jobs/clear": api.clear_jobs,
        "/api/reveal": api.reveal,
        "/api/open-folder": api.open_folder,
        "/api/choose-folder": api.choose_folder,
        "/api/settings": api.update_settings,
    }
