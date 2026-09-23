"""Batch 6 dates and timezones: flights dated by the local day of takeoff on
every import path, the backfill migration, month-based maintenance intervals,
and the digest's "already sent today" check."""

import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from alembic import command
from alembic.config import Config

import app.config
from app.models.flight import Flight
from app.models.notification_log import NotificationLog
from app.models.setting import Setting
from app.routers.maintenance_schedules import _calc_next_due
from app.services import sync_manager
from app.services.local_time import local_flight_date
from app.services.sync_manager import SyncResult

CHICAGO = ZoneInfo("America/Chicago")
# 21:30 on New Year's Eve in Chicago, already January 1 in UTC.
EVENING_UTC = datetime(2026, 1, 1, 3, 30)


@pytest.fixture
def chicago(db):
    db.add(Setting(key="display_timezone", value="America/Chicago"))
    db.commit()


# 1. The helper ---------------------------------------------------------------------

def test_evening_takeoff_is_dated_by_the_local_day():
    assert local_flight_date(EVENING_UTC, CHICAGO) == date(2025, 12, 31)
    assert local_flight_date(EVENING_UTC.replace(tzinfo=timezone.utc), CHICAGO) == date(2025, 12, 31)
    assert local_flight_date(datetime(2026, 1, 1, 18, 0), CHICAGO) == date(2026, 1, 1)
    assert local_flight_date(None, CHICAGO) is None


# 2. Every path that creates or refreshes a flight ------------------------------------

def test_skydio_sync_dates_a_flight_by_its_local_day(db, chicago):
    rows = [{"external_id": "EVE-1", "takeoff_time": EVENING_UTC.replace(tzinfo=timezone.utc), "date": "2026-01-01"}]
    sync_manager._upsert_flights(rows, [], db, SyncResult())
    db.commit()
    assert db.query(Flight).one().date == date(2025, 12, 31)


def test_skydio_enrichment_dates_by_the_local_day(db, chicago):
    flight = Flight(external_id="EVE-2", api_provider="skydio")
    sync_manager._enrich_flight_timestamps(flight, {"takeoff_time": "2026-01-01T03:30:00Z"}, CHICAGO)
    assert flight.date == date(2025, 12, 31)


def test_enrich_route_dates_by_the_local_day(db, chicago):
    from app.routers.sync import _enrich_timestamps
    flight = Flight(external_id="EVE-3")
    _enrich_timestamps(flight, {"takeoff_time": "2026-01-01T03:30:00Z"}, CHICAGO)
    assert flight.date == date(2025, 12, 31)


def test_refresh_dates_by_the_local_day(db, chicago):
    from app.routers.flights import _refresh_timestamps
    flight = Flight(external_id="EVE-4")
    _refresh_timestamps(flight, {"takeoff_time": "2026-01-01T03:30:00Z"}, [], CHICAGO)
    assert flight.date == date(2025, 12, 31)


@pytest.mark.parametrize("source,expected", [
    ("airdata_json", date(2025, 12, 31)),   # UTC log: redated to the local day
    ("parrot_gutma", date(2026, 1, 1)),     # already local wall-clock: kept
])
def test_flight_log_import_dates_by_the_local_day(db, chicago, source, expected):
    from app.services.flight_log_import import _flight_from_metadata
    meta = {"takeoff_time": EVENING_UTC, "date": EVENING_UTC.date()}
    assert _flight_from_metadata(meta, source, None, db).date == expected


# 3. The backfill migration -------------------------------------------------------------

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"


def _alembic(url):
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def test_backfill_redates_only_utc_dated_rows_from_utc_sources(tmp_path, monkeypatch):
    path = tmp_path / "m.db"
    url = f"sqlite:///{path.as_posix()}"
    monkeypatch.setattr(app.config.settings, "DATABASE_URL", url)
    command.upgrade(_alembic(url), "0007_evidence_soft_delete")

    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO settings (key, value) VALUES ('display_timezone', 'America/Chicago')")
    rows = {
        "utc_dated": ("skydio_api", "2026-01-01", "2026-01-01 03:30:00.000000"),
        "hand_fixed": ("skydio_api", "2025-12-31", "2026-01-01 03:30:00.000000"),
        "daytime": ("skydio_api", "2026-01-01", "2026-01-01 18:00:00.000000"),
        "manual": ("manual", "2026-01-01", "2026-01-01 03:30:00.000000"),
        "parrot": ("parrot_gutma", "2026-01-01", "2026-01-01 03:30:00.000000"),
        "brinc": ("brinc_csv", "2026-01-01", "2026-01-01 03:30:00.000000"),
    }
    ids = {}
    for name, (source, day, takeoff) in rows.items():
        cur = conn.execute(
            "INSERT INTO flights (data_source, date, takeoff_time, review_status, pilot_confirmed, "
            "counts_toward_totals, has_telemetry, telemetry_synced) VALUES (?, ?, ?, 'needs_review', 0, 1, 0, 0)",
            (source, day, takeoff))
        ids[name] = cur.lastrowid
    conn.commit()
    conn.close()

    command.upgrade(_alembic(url), "head")

    conn = sqlite3.connect(path)
    dates = {name: conn.execute("SELECT date FROM flights WHERE id = ?", (i,)).fetchone()[0] for name, i in ids.items()}
    conn.close()
    assert dates == {
        "utc_dated": "2025-12-31",
        "hand_fixed": "2025-12-31",
        "daytime": "2026-01-01",
        "manual": "2026-01-01",
        "parrot": "2026-01-01",
        "brinc": "2025-12-31",
    }


# 4. Maintenance intervals are calendar months ---------------------------------------

@pytest.mark.parametrize("frequency,start,expected", [
    ("monthly", date(2026, 1, 15), date(2026, 2, 15)),
    ("monthly", date(2026, 1, 31), date(2026, 2, 28)),
    ("quarterly", date(2026, 11, 30), date(2027, 2, 28)),
    ("yearly", date(2028, 2, 29), date(2029, 2, 28)),
    ("yearly", date(2026, 3, 1), date(2027, 3, 1)),
    ("three_years", date(2026, 6, 10), date(2029, 6, 10)),
])
def test_next_due_moves_by_calendar_months(frequency, start, expected):
    assert _calc_next_due(frequency, start) == expected


def test_unknown_frequency_is_refused(client, admin_headers):
    resp = client.post("/api/maintenance/schedules", headers=admin_headers, json={
        "name": "Weekly wash", "entity_type": "organization", "frequency": "weekly"})
    assert resp.status_code == 422


# 5. The digest's "already sent today" uses one clock ---------------------------------

def test_digest_sent_before_local_midnight_does_not_block_today(db, admin_user):
    from app.services.scheduler import _is_pref_due_now
    local_midnight_utc = (datetime.combine(date.today(), datetime.min.time())
                          .astimezone(timezone.utc).replace(tzinfo=None))
    db.add(NotificationLog(user_id=admin_user.id, subject="s", status="sent",
                           sent_at=local_midnight_utc - timedelta(minutes=1)))
    db.commit()
    pref = SimpleNamespace(user_id=admin_user.id, send_time="07:00", frequency="daily", send_day=None)
    assert _is_pref_due_now(pref, datetime.now(), "07", db) is True


def test_digest_already_sent_today_is_not_resent(db, admin_user):
    from app.services.scheduler import _is_pref_due_now
    db.add(NotificationLog(user_id=admin_user.id, subject="s", status="sent",
                           sent_at=datetime.now(timezone.utc).replace(tzinfo=None)))
    db.commit()
    pref = SimpleNamespace(user_id=admin_user.id, send_time="07:00", frequency="daily", send_day=None)
    assert _is_pref_due_now(pref, datetime.now(), "07", db) is False
