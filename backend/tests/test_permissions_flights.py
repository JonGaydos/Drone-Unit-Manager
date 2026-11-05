"""Flight routes enforce the role permission grid, including record ownership."""

from datetime import date

from app.models.audit_log import AuditLog
from app.models.flight import Flight
from app.models.pilot import Pilot
from app.models.user import User

PERMISSIONS_URL = "/api/permissions"
FLIGHTS_URL = "/api/flights"
NEEDS_REVIEW = "needs_review"
REVIEWED = "reviewed"


def _grid(client, headers, *changes):
    body = {"changes": [{"role": r, "key": k, "value": v} for r, k, v in changes]}
    resp = client.put(PERMISSIONS_URL, headers=headers, json=body)
    assert resp.status_code == 200, resp.text


def _flight(db, **kwargs):
    kwargs.setdefault("review_status", NEEDS_REVIEW)
    kwargs.setdefault("date", date(2026, 1, 5))
    flight = Flight(**kwargs)
    db.add(flight)
    db.commit()
    db.refresh(flight)
    return flight


def _other_pilot(db):
    pilot = Pilot(first_name="Other", last_name="Pilot")
    db.add(pilot)
    db.commit()
    db.refresh(pilot)
    return pilot


def test_pilot_cannot_delete_flight_by_default(client, db, pilot_headers, linked_pilot):
    flight = _flight(db, pilot_id=linked_pilot.id)
    assert client.delete(f"{FLIGHTS_URL}/{flight.id}", headers=pilot_headers).status_code == 403


def test_supervisor_can_delete(client, db, supervisor_headers):
    flight = _flight(db)
    assert client.delete(f"{FLIGHTS_URL}/{flight.id}", headers=supervisor_headers).status_code == 200


def test_pilot_delete_when_set_to_own(client, db, admin_headers, pilot_headers, linked_pilot):
    _grid(client, admin_headers, ("pilot", "flights.delete", "own"))
    mine = _flight(db, pilot_id=linked_pilot.id)
    theirs = _flight(db, pilot_id=_other_pilot(db).id)
    assert client.delete(f"{FLIGHTS_URL}/{mine.id}", headers=pilot_headers).status_code == 200
    assert client.delete(f"{FLIGHTS_URL}/{theirs.id}", headers=pilot_headers).status_code == 403


def test_pilot_edit_own_flight(client, db, pilot_headers, linked_pilot):
    flight = _flight(db, pilot_id=linked_pilot.id)
    resp = client.patch(f"{FLIGHTS_URL}/{flight.id}", headers=pilot_headers, json={"purpose": "Training"})
    assert resp.status_code == 200
    assert resp.json()["purpose"] == "Training"


def test_pilot_cannot_edit_others_flight(client, db, pilot_headers, linked_pilot):
    flight = _flight(db, pilot_id=_other_pilot(db).id)
    resp = client.patch(f"{FLIGHTS_URL}/{flight.id}", headers=pilot_headers, json={"purpose": "Training"})
    assert resp.status_code == 403


def test_own_edit_cannot_reassign_pilot(client, db, pilot_headers, linked_pilot):
    flight = _flight(db, pilot_id=linked_pilot.id)
    other = _other_pilot(db)
    url = f"{FLIGHTS_URL}/{flight.id}"
    assert client.patch(url, headers=pilot_headers, json={"pilot_id": other.id}).status_code == 403
    assert client.patch(url, headers=pilot_headers, json={"pilot_id": linked_pilot.id}).status_code == 200


def test_all_level_edit_can_reassign_pilot(client, db, supervisor_headers, linked_pilot):
    flight = _flight(db, pilot_id=linked_pilot.id)
    other = _other_pilot(db)
    resp = client.patch(f"{FLIGHTS_URL}/{flight.id}", headers=supervisor_headers, json={"pilot_id": other.id})
    assert resp.status_code == 200


def test_create_for_other_pilot_is_allowed_and_needs_review(client, pilot_headers, pilot_user, db, linked_pilot):
    other = _other_pilot(db)
    resp = client.post(FLIGHTS_URL, headers=pilot_headers, json={"pilot_id": other.id, "date": "2026-02-01"})
    assert resp.status_code == 200
    assert resp.json()["review_status"] == NEEDS_REVIEW
    flight = db.query(Flight).filter(Flight.id == resp.json()["id"]).one()
    assert flight.created_by_id == pilot_user.id


def test_creator_can_edit_flight_logged_for_other(client, db, pilot_headers, linked_pilot):
    other = _other_pilot(db)
    created = client.post(FLIGHTS_URL, headers=pilot_headers, json={"pilot_id": other.id}).json()
    resp = client.patch(f"{FLIGHTS_URL}/{created['id']}", headers=pilot_headers, json={"purpose": "Training"})
    assert resp.status_code == 200


def test_supervisor_created_flight_needs_review(client, supervisor_headers):
    resp = client.post(FLIGHTS_URL, headers=supervisor_headers, json={"date": "2026-02-01"})
    assert resp.status_code == 200
    assert resp.json()["review_status"] == NEEDS_REVIEW


def test_edit_of_reviewed_flight_returns_to_queue(client, db, pilot_headers, linked_pilot):
    flight = _flight(db, pilot_id=linked_pilot.id, review_status=REVIEWED, purpose="Patrol")
    resp = client.patch(f"{FLIGHTS_URL}/{flight.id}", headers=pilot_headers, json={"purpose": "Training"})
    assert resp.status_code == 200
    assert resp.json()["review_status"] == NEEDS_REVIEW


def test_edit_echoing_values_keeps_reviewed(client, db, pilot_headers, linked_pilot):
    flight = _flight(db, pilot_id=linked_pilot.id, review_status=REVIEWED, purpose="Patrol")
    body = {"purpose": "Patrol", "pilot_id": linked_pilot.id, "review_status": REVIEWED}
    resp = client.patch(f"{FLIGHTS_URL}/{flight.id}", headers=pilot_headers, json=body)
    assert resp.status_code == 200
    assert resp.json()["review_status"] == REVIEWED


def test_supervisor_edit_keeps_reviewed(client, db, supervisor_headers):
    flight = _flight(db, review_status=REVIEWED, purpose="Patrol")
    resp = client.patch(f"{FLIGHTS_URL}/{flight.id}", headers=supervisor_headers, json={"purpose": "Training"})
    assert resp.status_code == 200
    assert resp.json()["review_status"] == REVIEWED


def test_review_holder_role_can_change_review_fields(client, db, admin_headers, pilot_headers, linked_pilot):
    _grid(client, admin_headers, ("pilot", "flights.review", "yes"))
    flight = _flight(db, pilot_id=linked_pilot.id)
    resp = client.patch(f"{FLIGHTS_URL}/{flight.id}", headers=pilot_headers, json={"review_status": REVIEWED})
    assert resp.status_code == 200
    assert resp.json()["review_status"] == REVIEWED


def test_pilot_cannot_change_review_fields(client, db, pilot_headers, linked_pilot):
    flight = _flight(db, pilot_id=linked_pilot.id)
    resp = client.patch(f"{FLIGHTS_URL}/{flight.id}", headers=pilot_headers, json={"review_status": REVIEWED})
    assert resp.status_code == 403


def test_unlinked_login_owns_only_what_it_logged(client, db, pilot_headers, pilot_user):
    assert pilot_user.pilot_id is None
    unassigned = _flight(db)
    assert client.patch(f"{FLIGHTS_URL}/{unassigned.id}", headers=pilot_headers, json={"purpose": "X"}).status_code == 403
    created = client.post(FLIGHTS_URL, headers=pilot_headers, json={}).json()
    assert client.patch(f"{FLIGHTS_URL}/{created['id']}", headers=pilot_headers, json={"purpose": "X"}).status_code == 200


def test_viewer_cannot_create_edit_delete(client, db, viewer_headers):
    flight = _flight(db)
    url = f"{FLIGHTS_URL}/{flight.id}"
    assert client.post(FLIGHTS_URL, headers=viewer_headers, json={}).status_code == 403
    assert client.patch(url, headers=viewer_headers, json={"purpose": "X"}).status_code == 403
    assert client.delete(url, headers=viewer_headers).status_code == 403
    assert client.get(url, headers=viewer_headers).status_code == 200


def test_review_actions_follow_flights_review(client, db, admin_headers, pilot_headers, supervisor_headers):
    flight = _flight(db)
    calls = [
        ("post", f"{FLIGHTS_URL}/bulk-update", {"flight_ids": [flight.id], "review_status": REVIEWED}),
        ("patch", f"{FLIGHTS_URL}/{flight.id}/telemetry-status", {"telemetry_synced": True}),
        ("patch", f"{FLIGHTS_URL}/{flight.id}/review-status", {"review_status": REVIEWED}),
    ]
    delete_call = ("post", f"{FLIGHTS_URL}/bulk-delete", {"flight_ids": [flight.id]})
    for method, url, body in calls + [delete_call]:
        assert getattr(client, method)(url, headers=pilot_headers, json=body).status_code == 403, url
    _grid(client, admin_headers, ("supervisor", "flights.review", "no"))
    for method, url, body in calls + [delete_call]:
        assert getattr(client, method)(url, headers=supervisor_headers, json=body).status_code == 403, url
    _grid(client, admin_headers, ("pilot", "flights.review", "yes"))
    for method, url, body in calls:
        assert getattr(client, method)(url, headers=pilot_headers, json=body).status_code == 200, url


def _bulk_delete(client, headers, flight_id):
    return client.post(f"{FLIGHTS_URL}/bulk-delete", headers=headers, json={"flight_ids": [flight_id]})


def _bulk_update(client, headers, flight, **fields):
    return client.post(f"{FLIGHTS_URL}/bulk-update", headers=headers, json={"flight_ids": [flight.id], **fields})


def test_bulk_delete_needs_delete_at_all(client, db, admin_headers, supervisor_headers):
    flight_id = _flight(db).id
    _grid(client, admin_headers, ("supervisor", "flights.delete", "none"))
    assert _bulk_delete(client, supervisor_headers, flight_id).status_code == 403
    _grid(client, admin_headers, ("supervisor", "flights.delete", "own"))
    assert _bulk_delete(client, supervisor_headers, flight_id).status_code == 403
    db.expire_all()
    assert db.query(Flight).filter(Flight.id == flight_id).first() is not None
    _grid(client, admin_headers, ("supervisor", "flights.delete", "all"))
    assert _bulk_delete(client, supervisor_headers, flight_id).status_code == 200
    db.expire_all()
    assert db.query(Flight).filter(Flight.id == flight_id).first() is None


def test_bulk_delete_with_delete_but_no_review_is_refused(client, db, admin_headers, pilot_headers):
    flight_id = _flight(db).id
    _grid(client, admin_headers, ("pilot", "flights.delete", "all"))
    assert _bulk_delete(client, pilot_headers, flight_id).status_code == 403


def test_bulk_pilot_and_purpose_changes_need_edit_at_all(client, db, admin_headers, supervisor_headers):
    other = _other_pilot(db)
    flight = _flight(db, purpose="Patrol")
    for level in ("none", "own"):
        _grid(client, admin_headers, ("supervisor", "flights.edit", level))
        assert _bulk_update(client, supervisor_headers, flight, purpose="Search").status_code == 403
        assert _bulk_update(client, supervisor_headers, flight, pilot_id=other.id).status_code == 403
    db.expire_all()
    stored = db.query(Flight).filter(Flight.id == flight.id).one()
    assert (stored.purpose, stored.pilot_id) == ("Patrol", None)
    _grid(client, admin_headers, ("supervisor", "flights.edit", "all"))
    assert _bulk_update(client, supervisor_headers, flight, purpose="Search", pilot_id=other.id).status_code == 200
    db.expire_all()
    stored = db.query(Flight).filter(Flight.id == flight.id).one()
    assert (stored.purpose, stored.pilot_id) == ("Search", other.id)


def test_bulk_review_fields_need_only_review(client, db, admin_headers, supervisor_headers):
    flight = _flight(db)
    _grid(client, admin_headers, ("supervisor", "flights.edit", "none"))
    resp = _bulk_update(client, supervisor_headers, flight, review_status=REVIEWED, pilot_confirmed=True,
                        counts_toward_totals=False)
    assert resp.status_code == 200, resp.text
    db.expire_all()
    assert db.query(Flight).filter(Flight.id == flight.id).one().review_status == REVIEWED


def test_bulk_update_echoing_current_values_needs_only_review(client, db, admin_headers, supervisor_headers):
    flight = _flight(db, purpose="Patrol")
    _grid(client, admin_headers, ("supervisor", "flights.edit", "none"))
    assert _bulk_update(client, supervisor_headers, flight, purpose="Patrol").status_code == 200


def test_refresh_and_purpose_changes_stay_admin(client, db, supervisor_headers):
    flight = _flight(db)
    assert client.post(f"{FLIGHTS_URL}/{flight.id}/refresh", headers=supervisor_headers).status_code == 403
    assert client.post(f"{FLIGHTS_URL}/purposes", headers=supervisor_headers, json={"name": "X"}).status_code == 403


def test_purposes_list_stays_signed_in_and_usage_needs_review(client, pilot_headers, supervisor_headers):
    assert client.get(f"{FLIGHTS_URL}/purposes/list", headers=pilot_headers).status_code == 200
    assert client.get(f"{FLIGHTS_URL}/purposes/usage", headers=pilot_headers).status_code == 403
    assert client.get(f"{FLIGHTS_URL}/purposes/usage", headers=supervisor_headers).status_code == 200


def test_view_off_hides_list_detail_count_review_telemetry(client, db, admin_headers, pilot_headers, linked_pilot):
    flight = _flight(db, pilot_id=linked_pilot.id)
    _grid(
        client, admin_headers,
        ("pilot", "flights.create", "no"), ("pilot", "flights.edit", "none"),
        ("pilot", "flights.view", "no"),
    )
    urls = [
        FLIGHTS_URL, f"{FLIGHTS_URL}/count", f"{FLIGHTS_URL}/review",
        f"{FLIGHTS_URL}/{flight.id}", f"{FLIGHTS_URL}/preflight-check?vehicle_id=1",
        f"/api/telemetry/flight/{flight.id}",
    ]
    for url in urls:
        assert client.get(url, headers=pilot_headers).status_code == 403, url


def test_delete_user_who_logged_a_flight(client, db, admin_headers, pilot_user, pilot_headers):
    created = client.post(FLIGHTS_URL, headers=pilot_headers, json={}).json()
    user_id = pilot_user.id
    resp = client.delete(f"/api/auth/users/{user_id}", headers=admin_headers)
    assert resp.status_code == 409
    db.expire_all()
    assert db.query(User).filter(User.id == user_id).first() is not None
    assert db.query(Flight).filter(Flight.id == created["id"]).one().created_by_id == user_id
    assert db.query(AuditLog).filter(AuditLog.user_id == user_id).count() > 0


def test_delete_user_with_audit_history_says_to_deactivate(client, db, admin_headers, pilot_user):
    from app.models.audit_log import AuditLog
    db.add(AuditLog(user_id=pilot_user.id, user_name="Pilot", action="update", entity_type="flight"))
    db.commit()

    resp = client.delete(f"/api/auth/users/{pilot_user.id}", headers=admin_headers)

    assert resp.status_code == 409
    assert "Deactivate" in resp.json()["detail"]
    db.expire_all()
    assert db.get(type(pilot_user), pilot_user.id) is not None
