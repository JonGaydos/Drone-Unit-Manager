"""Long work run on a thread, with its status kept for the page to poll.

A manual sync can run for minutes. Behind Cloudflare a request that has not
answered in 100 seconds is cut off, so the browser reported a failure while
the sync carried on. The start routes now hand the work to a job and answer at
once, and the page polls the job until it finishes. Jobs live in memory: the
app runs one process, and a job does not outlive the process running it.
"""

import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Callable

logger = logging.getLogger(__name__)

# Finished jobs kept for polling; the oldest go first.
MAX_KEPT = 20

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _prune() -> None:
    finished = [j for j in _jobs.values() if j["status"] != "running"]
    finished.sort(key=lambda j: j["finished_at"])
    for job in finished[:max(0, len(_jobs) - MAX_KEPT)]:
        del _jobs[job["id"]]


def start(kind: str, work: Callable[[], dict], on_finish: Callable[[], None] | None = None) -> str:
    """Run ``work`` on a thread and return the job id at once.

    ``work`` returns the result to report; an exception marks the job failed.
    ``on_finish`` runs afterwards either way (a caller releases a lock here).
    """
    job_id = uuid.uuid4().hex
    job = {"id": job_id, "kind": kind, "status": "running", "started_at": _now(),
           "finished_at": None, "result": None, "error": None}
    with _jobs_lock:
        _prune()
        _jobs[job_id] = job

    def run():
        status = "failed"
        try:
            job["result"] = work()
            status = "done"
        except Exception as exc:
            logger.exception("Job %s (%s) failed", job_id, kind)
            job["error"] = str(exc)
        finally:
            # finished_at before status: a poller that sees the job finished
            # also sees when, and pruning never sorts a finished job without one.
            job["finished_at"] = _now()
            job["status"] = status
            if on_finish:
                on_finish()

    threading.Thread(target=run, name=f"job-{kind}", daemon=True).start()
    return job_id


def get(job_id: str) -> dict | None:
    """A copy of the job's current state, or None if unknown."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None
