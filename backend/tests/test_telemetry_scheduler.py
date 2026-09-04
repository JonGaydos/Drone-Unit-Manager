"""Scheduled telemetry job: runs batch when flights are missing telemetry,
skips (no Skydio call) when none are, and reschedule adds/removes the job."""
import pytest
from apscheduler.schedulers.background import BackgroundScheduler

import app.services.scheduler as sched
from app.models.flight import Flight
from app.models.setting import Setting
from app.services.sync_manager import SyncManager


@pytest.fixture
def scheduler_db(_engines, monkeypatch):
    """Point the scheduler module's SessionLocal at the temp engine."""
    TestingSessionLocal, _ = _engines
    monkeypatch.setattr(sched, "SessionLocal", TestingSessionLocal)
    return TestingSessionLocal


def _seed_token(db):
    db.add(Setting(key="skydio_api_token", value="test-token"))
    db.commit()


def test_scheduled_telemetry_runs_batch_when_missing(db, scheduler_db, monkeypatch):
    _seed_token(db)
    db.add(Flight(external_id="F1", api_provider="skydio", telemetry_synced=False))
    db.commit()

    calls = []
    monkeypatch.setattr(SyncManager, "batch_sync_telemetry",
                        staticmethod(lambda session, limit=10: calls.append(limit) or 1))

    sched._run_scheduled_telemetry_sync()

    assert calls == [10]


def test_scheduled_telemetry_skips_when_none_missing(db, scheduler_db, monkeypatch):
    _seed_token(db)
    # No unsynced flights present.
    calls = []
    monkeypatch.setattr(SyncManager, "batch_sync_telemetry",
                        staticmethod(lambda session, limit=10: calls.append(limit) or 0))

    sched._run_scheduled_telemetry_sync()

    assert calls == []  # guard returned before touching the batch / Skydio


def test_scheduled_telemetry_skips_without_token(db, scheduler_db, monkeypatch):
    db.add(Flight(external_id="F2", api_provider="skydio", telemetry_synced=False))
    db.commit()
    calls = []
    monkeypatch.setattr(SyncManager, "batch_sync_telemetry",
                        staticmethod(lambda session, limit=10: calls.append(limit) or 0))

    sched._run_scheduled_telemetry_sync()

    assert calls == []  # no token -> no work


def test_reschedule_telemetry_adds_and_removes_job(monkeypatch):
    s = BackgroundScheduler()
    s.start()
    monkeypatch.setattr(sched, "_scheduler", s)
    try:
        sched.reschedule_telemetry_sync(30)
        assert s.get_job(sched.TELEMETRY_SYNC_JOB_ID) is not None
        sched.reschedule_telemetry_sync(None)
        assert s.get_job(sched.TELEMETRY_SYNC_JOB_ID) is None
    finally:
        s.shutdown(wait=False)


def test_get_telemetry_interval_reads_setting(db, scheduler_db):
    db.add(Setting(key="telemetry_sync_interval", value="60"))
    db.commit()
    assert sched._get_telemetry_sync_interval_minutes() == 60


def test_get_telemetry_interval_none_when_empty(db, scheduler_db):
    db.add(Setting(key="telemetry_sync_interval", value=""))
    db.commit()
    assert sched._get_telemetry_sync_interval_minutes() is None
