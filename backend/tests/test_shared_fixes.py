"""Regression tests for the Area 10 staging-test fixes: field clearing and
error mapping (backlog A-F31, B-23, C-F21, B-5, C-F3, D-4)."""

from datetime import date

from app.models import Battery, Dock, Vehicle


# --- A-F31: fleet edits clear a field sent as null ---------------------------

def test_vehicle_patch_null_clears_optional_fields(client, db, admin_headers):
    v = Vehicle(serial_number="AREA10-V1", manufacturer="Acme", model="Quad", nickname="Kite",
                notes="Old note", acquired_date=date(2025, 1, 2))
    db.add(v)
    db.commit()

    resp = client.patch(f"/api/vehicles/{v.id}", headers=admin_headers,
                        json={"nickname": None, "notes": None, "acquired_date": None})

    assert resp.status_code == 200, resp.text
    db.expire_all()
    stored = db.get(Vehicle, v.id)
    assert (stored.nickname, stored.notes, stored.acquired_date) == (None, None, None)


def test_battery_patch_null_clears_health_and_dates(client, db, admin_headers):
    b = Battery(serial_number="AREA10-B1", health_pct=88, acquired_date=date(2025, 1, 2),
                decommissioned_date=date(2026, 1, 2))
    db.add(b)
    db.commit()

    resp = client.patch(f"/api/batteries/{b.id}", headers=admin_headers,
                        json={"health_pct": None, "acquired_date": None, "decommissioned_date": None})

    assert resp.status_code == 200, resp.text
    db.expire_all()
    stored = db.get(Battery, b.id)
    assert (stored.health_pct, stored.acquired_date, stored.decommissioned_date) == (None, None, None)


def test_dock_patch_null_clears_coordinates(client, db, admin_headers):
    d = Dock(serial_number="AREA10-D1", lat=30.1, lon=-85.1)
    db.add(d)
    db.commit()

    resp = client.patch(f"/api/docks/{d.id}", headers=admin_headers, json={"lat": None, "lon": None})

    assert resp.status_code == 200, resp.text
    db.expire_all()
    assert (db.get(Dock, d.id).lat, db.get(Dock, d.id).lon) == (None, None)
