"""One provider sync at a time.

A manual sync, an enrich pass, a telemetry batch and the scheduled jobs all
read the provider and write flights. Two at once insert the same flight twice
and fight over SQLite's single writer. The app runs one worker process
(see the Dockerfile CMD), so a process lock is enough.
"""

import threading
from contextlib import contextmanager

from fastapi import HTTPException

_lock = threading.Lock()

BUSY = "A sync is already running. Try again when it finishes."


class SyncBusy(Exception):
    """Raised when another sync holds the lock."""


@contextmanager
def sync_guard():
    """Hold the sync lock for the block, without waiting.

    Raises:
        SyncBusy: when another sync is running.
    """
    if not _lock.acquire(blocking=False):
        raise SyncBusy(BUSY)
    try:
        yield
    finally:
        _lock.release()


@contextmanager
def sync_guard_http():
    """sync_guard for a request handler: a busy lock is a 409."""
    try:
        with sync_guard():
            yield
    except SyncBusy:
        raise HTTPException(409, BUSY)
