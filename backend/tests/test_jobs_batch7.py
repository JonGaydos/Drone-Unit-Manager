"""Batch 7 long-running work: background sync jobs, restores that hold the sync
lock and keep off the event loop, scheduled backups that are complete or
absent (never half-written), and a generic import that survives bad rows,
skips repeats and says when it was cut short."""

import io
import json
import time
import zipfile
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.mission_log import MissionLog
from app.models.setting import Setting
from app.services import backup_jobs, jobs, sync_manager
from app.services.sync_lock import restoring, sync_guard


def _wait_for(client, headers, job_id, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/sync/jobs/{job_id}", headers=headers).json()
        if job["status"] != "running":
            return job
        time.sleep(0.05)
    raise AssertionError("job did not finish")


class _QuietProvider:
    """A provider with nothing to sync."""

    def __getattr__(self, name):
        if name == "get_flight_detail":
            return lambda creds, flight_id: None
        return lambda *a, **k: []


@pytest.fixture
def skydio(db, monkeypatch):
    db.add_all([Setting(key="skydio_api_token", value="t"), Setting(key="skydio_token_id", value="id")])
    db.commit()
    monkeypatch.setattr(sync_manager, "get_provider", lambda name: _QuietProvider())


# 1. The job runner ------------------------------------------------------------------

def test_job_reports_its_result_and_its_failure():
    ok = jobs.start("demo", lambda: {"n": 1})
    bad = jobs.start("demo", lambda: 1 / 0)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and "running" in (jobs.get(ok)["status"], jobs.get(bad)["status"]):
        time.sleep(0.01)
    assert jobs.get(ok)["status"] == "done"
    assert jobs.get(ok)["result"] == {"n": 1}
    assert jobs.get(bad)["status"] == "failed"
    assert "division" in jobs.get(bad)["error"]
    assert jobs.get("nope") is None


# 2. Sync runs as a job the page can poll ----------------------------------------------

def test_sync_job_runs_and_releases_the_lock(client, admin_headers, skydio):
    job_id = client.post("/api/sync/now/start", headers=admin_headers).json()["job_id"]
    job = _wait_for(client, admin_headers, job_id)
    assert job["status"] == "done"
    assert job["result"]["errors"] == []
    # The lock came back: another start is accepted.
    second = client.post("/api/sync/telemetry/start", headers=admin_headers)
    assert second.status_code == 200
    _wait_for(client, admin_headers, second.json()["job_id"])


def test_sync_job_start_is_refused_while_a_sync_runs(client, admin_headers):
    with sync_guard():
        assert client.post("/api/sync/now/start", headers=admin_headers).status_code == 409
        assert client.post("/api/sync/telemetry/start", headers=admin_headers).status_code == 409


def test_unknown_job_is_404(client, admin_headers):
    assert client.get("/api/sync/jobs/missing", headers=admin_headers).status_code == 404


def test_sync_jobs_are_admin_only(client, pilot_headers):
    assert client.post("/api/sync/now/start", headers=pilot_headers).status_code == 403


# 3. A restore holds the sync lock ---------------------------------------------------

def test_restore_is_refused_while_a_sync_runs(client, admin_headers):
    with sync_guard():
        resp = client.post("/api/backup/import", headers=admin_headers,
                           files={"file": ("b.zip", b"PK\x05\x06" + b"\x00" * 18, "application/zip")})
    assert resp.status_code == 409


# 4. Scheduled backups ------------------------------------------------------------------

@pytest.fixture
def backup_env(db, tmp_path, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path / "uploads")
    (tmp_path / "uploads").mkdir()
    monkeypatch.setattr(backup_jobs, "SessionLocal", lambda: db)
    return tmp_path / "backups" / "app"


def test_scheduled_backup_includes_telemetry_and_leaves_no_partial_file(db, backup_env):
    backup_jobs.run_scheduled_backup()
    files = sorted(p.name for p in backup_env.iterdir())
    assert len(files) == 1
    assert files[0].endswith(".zip")
    with zipfile.ZipFile(backup_env / files[0]) as zf:
        assert json.loads(zf.read("manifest.json"))["include_telemetry"] is True


def test_failed_backup_leaves_no_file_behind(db, backup_env, monkeypatch):
    def half_written(db, include_telemetry=False):
        class Broken(io.BytesIO):
            def read(self, n=-1):
                raise OSError("disk went away")
        return Broken(b"x"), {}

    monkeypatch.setattr(backup_jobs, "build_backup_archive", half_written)
    backup_jobs.run_scheduled_backup()
    assert list(backup_env.iterdir()) == []
    assert json.loads(db.query(Setting).filter(Setting.key == "last_backup_result").one().value)["ok"] is False


def test_backup_is_skipped_during_a_restore(db, backup_env):
    with restoring():
        backup_jobs.run_scheduled_backup()
    assert not backup_env.exists() or list(backup_env.iterdir()) == []


@pytest.mark.parametrize("hours_ago,expect_run", [(None, True), (30, True), (2, False)])
def test_catch_up_backup_runs_only_when_the_last_is_stale(db, backup_env, monkeypatch, hours_ago, expect_run):
    if hours_ago is not None:
        stamp = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
        db.add(Setting(key="last_backup_at", value=stamp))
        db.commit()
    ran = []
    monkeypatch.setattr(backup_jobs, "run_scheduled_backup", lambda: ran.append(True))
    backup_jobs.run_catch_up_backup()
    assert bool(ran) is expect_run


# 5. Generic import -------------------------------------------------------------------------

MAPPING = json.dumps({"date": "Date", "title": "Title"})


def _import_url(client, headers, csv_text):
    return client.post(f"/api/import/commit?entity=missions&mapping={MAPPING}", headers=headers,
                       files={"file": ("m.csv", csv_text.encode(), "text/csv")})


def test_importing_the_same_file_twice_adds_nothing_the_second_time(client, db, admin_headers):
    csv_text = "Date,Title\n2026-09-01,Search A\n2026-09-02,Search B\n"
    first = _import_url(client, admin_headers, csv_text).json()
    second = _import_url(client, admin_headers, csv_text).json()
    assert (first["created"], second["created"], second["duplicates"]) == (2, 0, 2)
    assert db.query(MissionLog).count() == 2


def test_a_row_that_fails_does_not_take_the_import_with_it(client, db, admin_headers, monkeypatch):
    from app.routers import import_router
    real = import_router._build_mission_from_row

    def build(row, mapping, user_id):
        # Fails at flush, after the row is in the session: without a savepoint
        # this left the session unusable and the whole import rolled back.
        if row.get("Title") == "Bad":
            return MissionLog(date=date(2026, 9, 2), title=None, man_hours=0, status="completed"), ""
        return real(row, mapping, user_id)

    monkeypatch.setattr(import_router, "_build_mission_from_row", build)
    csv_text = "Date,Title\n2026-09-01,Good A\n2026-09-02,Bad\n2026-09-03,Good B\n"
    result = _import_url(client, admin_headers, csv_text).json()
    assert result["created"] == 2
    assert len(result["errors"]) == 1
    assert db.query(MissionLog).count() == 2


def test_a_file_over_the_row_cap_is_reported_as_cut_short(client, admin_headers):
    rows = "".join(f"2026-01-01,Mission {i}\n" for i in range(5001))
    resp = client.post("/api/import/preview?entity=missions", headers=admin_headers,
                       files={"file": ("m.csv", ("Date,Title\n" + rows).encode(), "text/csv")})
    assert resp.json()["truncated"] is True
    assert resp.json()["row_count"] == 5000
