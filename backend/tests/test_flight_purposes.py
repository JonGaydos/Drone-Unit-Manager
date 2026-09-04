"""Flight purpose management: usage counts, case-insensitive creation, and the
cascade that deleting a purpose performs.

A flight stores the purpose NAME rather than a foreign key, so deleting the
option used to leave flights holding a value that no longer appeared in any
list: not selectable, not removable, and invisible from the Settings editor.
"""

from datetime import date

from app.models.flight import Flight, FlightPurpose
from app.models.mission_log import MissionLog

PURPOSES = "/api/flights/purposes"


def _seed_purpose(db, name, sort_order=0):
    p = FlightPurpose(name=name, sort_order=sort_order, is_active=True)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _seed_flight(db, purpose, when=date(2026, 3, 1)):
    db.add(Flight(date=when, purpose=purpose))
    db.commit()


# --- Usage counts -----------------------------------------------------------


def test_usage_reports_how_many_records_reference_each_purpose(client, db, admin_headers):
    _seed_purpose(db, "Patrol")
    _seed_purpose(db, "Training")
    _seed_flight(db, "Patrol")
    _seed_flight(db, "Patrol")
    db.add(MissionLog(date=date(2026, 3, 2), title="Patrol run", reason="Patrol"))
    db.commit()

    rows = client.get(f"{PURPOSES}/usage", headers=admin_headers).json()

    by_name = {r["name"]: r for r in rows}
    assert by_name["Patrol"]["flight_count"] == 2
    assert by_name["Patrol"]["mission_count"] == 1
    assert by_name["Training"]["flight_count"] == 0
    assert by_name["Training"]["mission_count"] == 0


def test_usage_requires_a_supervisor(client, db, pilot_headers):
    _seed_purpose(db, "Patrol")
    assert client.get(f"{PURPOSES}/usage", headers=pilot_headers).status_code == 403


def test_usage_route_does_not_shadow_the_list_route(client, db, admin_headers):
    """/purposes/list and /purposes/usage are both literal paths; a regression
    here would silently swap what the flight pages load."""
    _seed_purpose(db, "Patrol")

    listed = client.get(f"{PURPOSES}/list", headers=admin_headers).json()

    assert [p["name"] for p in listed] == ["Patrol"]
    assert "flight_count" not in listed[0], "the cheap list route grew the expensive counts"


# --- Creation ---------------------------------------------------------------


def test_creating_a_purpose_differing_only_in_case_is_rejected(client, db, admin_headers):
    """How "CPTED" and "CPTEd" both ended up in the list."""
    _seed_purpose(db, "CPTED")

    resp = client.post(PURPOSES, headers=admin_headers, json={"name": "CPTEd"})

    assert resp.status_code == 400
    assert "CPTED" in resp.json()["detail"]


def test_creating_a_purpose_trims_and_rejects_blank(client, db, admin_headers):
    created = client.post(PURPOSES, headers=admin_headers, json={"name": "  Night Ops  "})
    assert created.status_code == 200, created.text
    assert created.json()["name"] == "Night Ops"

    assert client.post(PURPOSES, headers=admin_headers, json={"name": "   "}).status_code == 400


# --- Deletion cascade -------------------------------------------------------


def test_deleting_a_purpose_clears_it_from_every_flight(client, db, admin_headers):
    purpose = _seed_purpose(db, "Mapping")
    _seed_flight(db, "Mapping")
    _seed_flight(db, "Mapping")
    _seed_flight(db, "Patrol")

    resp = client.delete(f"{PURPOSES}/{purpose.id}", headers=admin_headers)

    assert resp.status_code == 200, resp.text
    assert resp.json()["flights_cleared"] == 2
    db.expire_all()
    purposes = [f.purpose for f in db.query(Flight).all()]
    assert sorted(p or "none" for p in purposes) == ["Patrol", "none", "none"]


def test_deleting_a_purpose_leaves_mission_reasons_intact(client, db, admin_headers):
    """Mission "reason" is written prose, not a picked option; the delete
    reports it rather than silently blanking it."""
    purpose = _seed_purpose(db, "Mapping")
    db.add(MissionLog(date=date(2026, 3, 2), title="Survey", reason="Mapping"))
    db.commit()

    resp = client.delete(f"{PURPOSES}/{purpose.id}", headers=admin_headers)

    assert resp.json()["missions_untouched"] == 1
    db.expire_all()
    assert db.query(MissionLog).one().reason == "Mapping"


def test_deleting_a_purpose_nothing_uses_reports_zero(client, db, admin_headers):
    purpose = _seed_purpose(db, "Unused")

    resp = client.delete(f"{PURPOSES}/{purpose.id}", headers=admin_headers)

    assert resp.json() == {"ok": True, "flights_cleared": 0, "missions_untouched": 0}
    assert db.query(FlightPurpose).count() == 0


def test_deleting_a_purpose_leaves_similarly_named_ones_alone(client, db, admin_headers):
    """Deleting "CPTEd" must not touch flights logged against "CPTED"."""
    wrong = _seed_purpose(db, "CPTEd")
    _seed_purpose(db, "CPTED")
    _seed_flight(db, "CPTEd")
    _seed_flight(db, "CPTED")

    client.delete(f"{PURPOSES}/{wrong.id}", headers=admin_headers)

    db.expire_all()
    remaining = sorted((f.purpose or "none") for f in db.query(Flight).all())
    assert remaining == ["CPTED", "none"]
    assert [p.name for p in db.query(FlightPurpose).all()] == ["CPTED"]


def test_deleting_an_unknown_purpose_is_a_404(client, admin_headers):
    assert client.delete(f"{PURPOSES}/9999", headers=admin_headers).status_code == 404
