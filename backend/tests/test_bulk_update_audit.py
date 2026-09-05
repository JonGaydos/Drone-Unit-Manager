"""A bulk edit must leave a record of what it overwrote.

On 2026-09-03 a single bulk edit set ``purpose="Search Warrant"`` on 100
flights. The audit entry read, in full, "Updated 100 flights". Reconstructing
which flights had changed, and to what, meant diffing the previous night's
backup.

These cover the two things that would have made that a five-minute fix: the
prior values are summarised into the audit ``changes`` payload, and the ids the
edit touched are named in ``details``.
"""

from datetime import date

from app.models.audit_log import AuditLog
from app.models.flight import Flight
from app.models.pilot import Pilot
from app.routers.flights import _id_ranges

BULK_UPDATE_URL = "/api/flights/bulk-update"


def _seed_flights(db, purposes):
    flights = [Flight(date=date(2025, 6, 1), purpose=p) for p in purposes]
    db.add_all(flights)
    db.commit()
    for flight in flights:
        db.refresh(flight)
    return flights


def _latest_audit(db):
    return db.query(AuditLog).order_by(AuditLog.id.desc()).first()


# 1. The prior values survive the edit ------------------------------------

def test_the_overwritten_purposes_are_recorded_most_common_first(client, db, admin_headers):
    """The shape of the incident: many rows, several prior purposes, one new
    value. The audit entry has to say which purposes were replaced and how many
    of each, or the edit is only undoable from a backup."""
    flights = _seed_flights(db, ["Map Scan"] * 3 + ["Training"] * 2 + ["Patrol"])

    resp = client.post(BULK_UPDATE_URL, headers=admin_headers, json={
        "flight_ids": [f.id for f in flights], "purpose": "Search Warrant"})
    assert resp.status_code == 200, resp.text

    db.expire_all()
    changes = _latest_audit(db).changes
    assert changes["purpose"]["new"] == "Search Warrant"
    assert changes["purpose"]["old"] == "Map Scan (3), Training (2), Patrol (1)"


def test_rows_that_already_hold_the_new_value_are_not_counted_as_overwritten(client, db, admin_headers):
    """Selecting a page and setting a purpose usually includes rows that already
    have it. Those are not losses and must not inflate the record."""
    flights = _seed_flights(db, ["Search Warrant", "Search Warrant", "Map Scan"])

    client.post(BULK_UPDATE_URL, headers=admin_headers, json={
        "flight_ids": [f.id for f in flights], "purpose": "Search Warrant"})

    db.expire_all()
    assert _latest_audit(db).changes["purpose"]["old"] == "Map Scan (1)"


def test_an_empty_prior_value_is_recorded_as_none_not_dropped(client, db, admin_headers):
    """A NULL purpose is still a value that was overwritten."""
    flights = _seed_flights(db, [None, None, "Map Scan"])

    client.post(BULK_UPDATE_URL, headers=admin_headers, json={
        "flight_ids": [f.id for f in flights], "purpose": "Search Warrant"})

    db.expire_all()
    assert _latest_audit(db).changes["purpose"]["old"] == "(none) (2), Map Scan (1)"


def test_an_edit_that_changes_nothing_says_so(client, db, admin_headers):
    flights = _seed_flights(db, ["Map Scan", "Map Scan"])

    client.post(BULK_UPDATE_URL, headers=admin_headers, json={
        "flight_ids": [f.id for f in flights], "purpose": "Map Scan"})

    db.expire_all()
    assert _latest_audit(db).changes["purpose"]["old"] == "(no change)"


def test_a_pilot_reassignment_records_the_pilot_ids_it_replaced(client, db, admin_headers):
    """Reassigning the pilot is the other bulk action that silently destroys
    what was there."""
    old_pilot = Pilot(first_name="Old", last_name="Pilot", status="active")
    new_pilot = Pilot(first_name="New", last_name="Pilot", status="active")
    db.add_all([old_pilot, new_pilot])
    db.commit()
    db.refresh(old_pilot)
    db.refresh(new_pilot)

    flights = [Flight(date=date(2025, 6, 1), pilot_id=old_pilot.id),
               Flight(date=date(2025, 6, 1), pilot_id=None)]
    db.add_all(flights)
    db.commit()
    for flight in flights:
        db.refresh(flight)

    client.post(BULK_UPDATE_URL, headers=admin_headers, json={
        "flight_ids": [f.id for f in flights], "pilot_id": new_pilot.id})

    db.expire_all()
    changes = _latest_audit(db).changes
    assert changes["pilot_id"]["new"] == str(new_pilot.id)
    assert str(old_pilot.id) in changes["pilot_id"]["old"]
    assert "(none)" in changes["pilot_id"]["old"]


def test_fields_the_request_omitted_are_absent_from_the_record(client, db, admin_headers):
    """Only what was actually set gets audited, so the entry reads as the edit
    that happened rather than every field the endpoint can touch."""
    flights = _seed_flights(db, ["Map Scan"])

    client.post(BULK_UPDATE_URL, headers=admin_headers, json={
        "flight_ids": [f.id for f in flights], "purpose": "Training"})

    db.expire_all()
    assert set(_latest_audit(db).changes) == {"purpose"}


def test_the_distinct_prior_values_are_capped(client, db, admin_headers):
    """Purpose is free text on import, so the number of distinct values an edit
    replaces is not bounded by the configured purpose list. Without a cap one
    edit can write an arbitrarily large blob into the audit table."""
    flights = _seed_flights(db, [f"Purpose {i}" for i in range(25)])

    client.post(BULK_UPDATE_URL, headers=admin_headers, json={
        "flight_ids": [f.id for f in flights], "purpose": "Search Warrant"})

    db.expire_all()
    old = _latest_audit(db).changes["purpose"]["old"]
    assert old.endswith(", and 15 more"), old
    assert old.count("Purpose ") == 10


# 2. Which flights were touched -------------------------------------------

def test_the_details_name_the_flights_the_edit_touched(client, db, admin_headers):
    flights = _seed_flights(db, ["Map Scan"] * 3)
    ids = sorted(f.id for f in flights)

    client.post(BULK_UPDATE_URL, headers=admin_headers, json={
        "flight_ids": ids, "purpose": "Training"})

    db.expire_all()
    details = _latest_audit(db).details
    assert details.startswith("Updated 3 flights")
    assert _id_ranges(ids) in details


def test_ids_that_do_not_exist_are_not_claimed_as_updated(client, db, admin_headers):
    """The endpoint updates the rows it finds. The record must reflect that, not
    the size of the request."""
    flights = _seed_flights(db, ["Map Scan"])

    resp = client.post(BULK_UPDATE_URL, headers=admin_headers, json={
        "flight_ids": [flights[0].id, 999_999], "purpose": "Training"})

    assert resp.json()["updated"] == 1
    db.expire_all()
    assert "999999" not in _latest_audit(db).details


def test_a_long_id_list_is_capped(client, db, admin_headers):
    """Every other flight, so the ranges cannot collapse. The detail column is
    read at a glance and must not become unbounded."""
    flights = _seed_flights(db, ["Map Scan"] * 400)
    ids = sorted(f.id for f in flights)[::2]

    client.post(BULK_UPDATE_URL, headers=admin_headers, json={
        "flight_ids": ids, "purpose": "Training"})

    db.expire_all()
    details = _latest_audit(db).details
    assert len(details) < 400
    assert details.endswith(", ...)"), details
    # The tail must be a whole id, not half of one.
    assert details.split(", ")[-2].isdigit(), details


# 3. The range compression itself -----------------------------------------

def test_id_ranges_collapses_runs():
    assert _id_ranges([1, 2, 3, 7, 8]) == "1-3, 7-8"


def test_id_ranges_keeps_isolated_ids_alone():
    assert _id_ranges([4, 9, 15]) == "4, 9, 15"


def test_id_ranges_sorts_and_deduplicates():
    assert _id_ranges([3, 1, 2, 2]) == "1-3"


def test_id_ranges_of_nothing_is_empty():
    assert _id_ranges([]) == ""


# 4. The edit still applies ------------------------------------------------

def test_the_flights_are_still_actually_updated(client, db, admin_headers):
    """The audit work sits in front of the write; the write must survive it."""
    flights = _seed_flights(db, ["Map Scan", "Training"])

    client.post(BULK_UPDATE_URL, headers=admin_headers, json={
        "flight_ids": [f.id for f in flights],
        "purpose": "Search Warrant", "review_status": "reviewed",
        "pilot_confirmed": True, "counts_toward_totals": False})

    db.expire_all()
    for flight in db.query(Flight).all():
        assert flight.purpose == "Search Warrant"
        assert flight.review_status == "reviewed"
        assert flight.pilot_confirmed is True
        assert flight.counts_toward_totals is False


def test_a_false_boolean_is_applied_not_treated_as_absent(client, db, admin_headers):
    """``counts_toward_totals=False`` is a real instruction. A None check that
    tested truthiness instead would silently drop it."""
    flights = _seed_flights(db, ["Map Scan"])

    client.post(BULK_UPDATE_URL, headers=admin_headers, json={
        "flight_ids": [f.id for f in flights], "counts_toward_totals": False})

    db.expire_all()
    assert db.query(Flight).one().counts_toward_totals is False
    assert set(_latest_audit(db).changes) == {"counts_toward_totals"}


def test_marking_reviewed_is_logged_as_an_approval(client, db, admin_headers):
    flights = _seed_flights(db, ["Map Scan"])

    client.post(BULK_UPDATE_URL, headers=admin_headers, json={
        "flight_ids": [f.id for f in flights], "review_status": "reviewed"})

    db.expire_all()
    assert _latest_audit(db).action == "bulk_approve"
