"""Vehicle matching between provider syncs and local records.

Skydio identifies aircraft by short name (e.g. "SkydioX2-7646") while
agencies often register the full airframe serial, so the sync falls back to
a case-insensitive nickname match and then stamps provider_serial so the
link survives later nickname changes. Vehicle merge likewise carries the
source's provider identity onto the keeper so a sync can't recreate the
duplicate it just removed.
"""

from app.models.vehicle import Vehicle
from app.services.sync_manager import SyncResult, _sync_vehicles

SHORT = "SkydioX2-7646"
FULL = "1668BE10JA007646"


class _StubProvider:
    def __init__(self, vehicles):
        self._vehicles = vehicles

    def sync_vehicles(self, creds):
        return self._vehicles


def _seed_vehicle(db, **kwargs):
    v = Vehicle(manufacturer="Skydio", model="X2E", **kwargs)
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def _run_sync(db, vehicles):
    result = SyncResult()
    _sync_vehicles(_StubProvider(vehicles), None, db, result)
    db.commit()
    return result


def test_sync_matches_by_nickname_and_backfills_provider_serial(db):
    v = _seed_vehicle(db, serial_number=FULL, nickname=SHORT)

    _run_sync(db, [{"serial_number": SHORT, "manufacturer": "Skydio", "model": "X2E"}])

    db.expire_all()
    assert db.query(Vehicle).count() == 1  # no duplicate created
    assert db.query(Vehicle).filter(Vehicle.id == v.id).one().provider_serial == SHORT


def test_sync_nickname_match_is_case_insensitive(db):
    _seed_vehicle(db, serial_number=FULL, nickname=SHORT.lower())

    _run_sync(db, [{"serial_number": SHORT}])

    db.expire_all()
    assert db.query(Vehicle).count() == 1


def test_sync_skips_ambiguous_nicknames(db):
    _seed_vehicle(db, serial_number=FULL, nickname=SHORT)
    _seed_vehicle(db, serial_number="OTHER-SERIAL", nickname=SHORT)

    _run_sync(db, [{"serial_number": SHORT}])

    db.expire_all()
    # Two records share the nickname, so the sync must not guess: it creates
    # its own record instead of updating the wrong one.
    assert db.query(Vehicle).count() == 3
    assert db.query(Vehicle).filter(Vehicle.serial_number == SHORT).count() == 1


def test_sync_still_prefers_provider_serial_over_nickname(db):
    linked = _seed_vehicle(db, serial_number=FULL, provider_serial=SHORT)
    _seed_vehicle(db, serial_number="OTHER-SERIAL", nickname=SHORT)

    _run_sync(db, [{"serial_number": SHORT, "nickname": "Falcon"}])

    db.expire_all()
    assert db.query(Vehicle).count() == 2
    assert db.query(Vehicle).filter(Vehicle.id == linked.id).one().nickname == "Falcon"


def test_provider_serial_is_editable_and_drives_matching(client, db, admin_headers):
    """An org can hand-link a vehicle to its API identity; the next sync
    matches on it even when serial and nickname are both custom."""
    v = _seed_vehicle(db, serial_number=FULL, nickname="Falcon")

    resp = client.patch(f"/api/vehicles/{v.id}", headers=admin_headers,
                        json={"provider_serial": SHORT})
    assert resp.status_code == 200, resp.text
    assert resp.json()["provider_serial"] == SHORT

    _run_sync(db, [{"serial_number": SHORT, "manufacturer": "Skydio", "model": "X2E"}])
    db.expire_all()
    assert db.query(Vehicle).count() == 1  # matched, no duplicate


def test_merge_keeper_adopts_provider_identity(client, db, admin_headers):
    keeper = _seed_vehicle(db, serial_number=FULL, nickname=SHORT)
    dup = _seed_vehicle(db, serial_number=SHORT, provider_serial=SHORT, api_provider="skydio")

    resp = client.post(f"/api/vehicles/{keeper.id}/merge?merge_from_id={dup.id}", headers=admin_headers)
    assert resp.status_code == 200, resp.text

    db.expire_all()
    kept = db.query(Vehicle).filter(Vehicle.id == keeper.id).one()
    assert kept.provider_serial == SHORT
    assert kept.api_provider == "skydio"
    assert db.query(Vehicle).count() == 1
