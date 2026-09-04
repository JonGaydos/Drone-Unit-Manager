"""Timezone serialization/normalization for flight datetimes."""
from datetime import datetime, timezone

from app.models.flight import Flight


def _make_flight(db, **kw):
    f = Flight(date=datetime(2026, 6, 24).date(), **kw)
    db.add(f)
    db.commit()
    db.refresh(f)
    return f


def test_flightout_serializes_naive_takeoff_as_utc_z(client, db, admin_headers):
    f = _make_flight(db, takeoff_time=datetime(2026, 6, 24, 16, 26, 0))
    resp = client.get(f"/api/flights/{f.id}", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["takeoff_time"] == "2026-06-24T16:26:00Z"


def test_patch_tz_aware_takeoff_is_stored_naive_utc(client, db, admin_headers):
    f = _make_flight(db, takeoff_time=datetime(2026, 6, 24, 16, 26, 0))
    # Client sends a Central-offset wall time; it must land in the DB as 16:26 UTC.
    resp = client.patch(
        f"/api/flights/{f.id}",
        json={"takeoff_time": "2026-06-24T11:26:00-05:00"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["takeoff_time"] == "2026-06-24T16:26:00Z"
    db.expire_all()
    stored = db.query(Flight).filter(Flight.id == f.id).first().takeoff_time
    assert stored.tzinfo is None
    assert stored == datetime(2026, 6, 24, 16, 26, 0)
