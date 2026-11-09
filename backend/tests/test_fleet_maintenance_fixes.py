"""Fleet and maintenance fixes from the 2026-11-08 staging test (Area 3)."""

from datetime import date


# ── A-F26: component dates ──────────────────────────────────────────────────

def _component(client, headers, **extra):
    resp = client.post("/api/components", headers=headers, json={
        "name": "Motor 1", "component_type": "motor", **extra,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_component_create_rejects_invalid_dates(client, admin_headers):
    for field in ("install_date", "warranty_expiry"):
        resp = client.post("/api/components", headers=admin_headers, json={
            "name": "x", "component_type": "motor", field: "2026-13-01",
        })
        assert resp.status_code == 422, f"{field}: {resp.text}"


def test_component_patch_rejects_invalid_date(client, admin_headers):
    cid = _component(client, admin_headers)["id"]
    resp = client.patch(f"/api/components/{cid}", headers=admin_headers,
                        json={"warranty_expiry": "not-a-date"})
    assert resp.status_code == 422, resp.text


def test_component_patch_empty_date_clears_it(client, admin_headers):
    cid = _component(client, admin_headers, install_date="2026-01-05")["id"]
    resp = client.patch(f"/api/components/{cid}", headers=admin_headers,
                        json={"install_date": ""})
    assert resp.status_code == 200, resp.text
    assert resp.json()["install_date"] is None


def test_component_valid_dates_round_trip(client, admin_headers):
    body = _component(client, admin_headers, install_date="2026-01-05",
                      warranty_expiry="2027-01-05")
    assert body["install_date"] == "2026-01-05"
    assert body["warranty_expiry"] == "2027-01-05"


# ── A-F1: vehicle create validation ─────────────────────────────────────────

def _vehicle(client, headers, **extra):
    payload = {"serial_number": "VEH-001", "manufacturer": "Acme", "model": "Hawk", **extra}
    resp = client.post("/api/vehicles", headers=headers, json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_vehicle_create_rejects_blank_required_fields(client, admin_headers):
    for field in ("serial_number", "manufacturer", "model"):
        for blank in ("", "   "):
            payload = {"serial_number": "VEH-B1", "manufacturer": "Acme", "model": "Hawk", field: blank}
            resp = client.post("/api/vehicles", headers=admin_headers, json=payload)
            assert resp.status_code == 422, f"{field}={blank!r}: {resp.text}"


def test_vehicle_patch_rejects_blank_required_fields(client, admin_headers):
    vid = _vehicle(client, admin_headers)["id"]
    for field in ("serial_number", "manufacturer", "model"):
        resp = client.patch(f"/api/vehicles/{vid}", headers=admin_headers, json={field: " "})
        assert resp.status_code == 422, f"{field}: {resp.text}"


def test_vehicle_create_trims_required_fields(client, admin_headers):
    body = _vehicle(client, admin_headers, serial_number="  VEH-T1 ", manufacturer=" Acme")
    assert body["serial_number"] == "VEH-T1"
    assert body["manufacturer"] == "Acme"


# ── A-F6: vehicle totals ────────────────────────────────────────────────────

def _flight(db, vehicle_id, seconds, **extra):
    from datetime import date as _date
    from app.models.flight import Flight
    f = Flight(vehicle_id=vehicle_id, date=_date(2026, 3, 1), duration_seconds=seconds, **extra)
    db.add(f)
    db.commit()
    return f


def test_vehicle_list_and_detail_carry_flight_totals(client, db, admin_headers):
    vid = _vehicle(client, admin_headers)["id"]
    _flight(db, vid, 3600)
    _flight(db, vid, 1800)

    listed = next(v for v in client.get("/api/vehicles", headers=admin_headers).json() if v["id"] == vid)
    assert listed["total_flights"] == 2
    assert listed["total_flight_hours"] == 1.5
    one = client.get(f"/api/vehicles/{vid}", headers=admin_headers).json()
    assert one["total_flights"] == 2
    assert one["total_flight_hours"] == 1.5


def test_vehicles_csv_totals_match_stats(client, db, admin_headers):
    import csv
    import io
    vid = _vehicle(client, admin_headers)["id"]
    _flight(db, vid, 7200)
    stats = client.get(f"/api/vehicles/{vid}/stats", headers=admin_headers).json()
    resp = client.get("/api/export/vehicles/csv", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    rows = list(csv.DictReader(io.StringIO(resp.text)))
    row = next(r for r in rows if r["Serial"] == "VEH-001")
    assert int(row["Flights"]) == stats["total_flights"] == 1
    assert float(row["Hours"]) == round(stats["total_flight_hours"], 1) == 2.0


# ── A-F23: equipment stats use the counted-flight scope ─────────────────────

def test_equipment_stats_skip_flights_that_do_not_count(client, db, admin_headers):
    from app.models.pilot import Pilot
    guest = Pilot(first_name="Guest", last_name="Operator", status="active", counts_toward_totals=False)
    db.add(guest)
    db.commit()
    vid = _vehicle(client, admin_headers)["id"]
    bid = client.post("/api/batteries", headers=admin_headers, json={"serial_number": "BAT-1"}).json()["id"]
    sid = client.post("/api/sensors", headers=admin_headers, json={"serial_number": "SEN-1"}).json()["id"]
    aid = client.post("/api/attachments", headers=admin_headers, json={"serial_number": "ATT-1"}).json()["id"]
    gear = dict(battery_serial="BAT-1", sensor_package="SEN-1", attachment_top="ATT-1")
    _flight(db, vid, 3600, **gear)
    _flight(db, vid, 999_999, counts_toward_totals=False, **gear)
    _flight(db, vid, 7200, pilot_id=guest.id, **gear)

    v = client.get(f"/api/vehicles/{vid}/stats", headers=admin_headers).json()
    assert v["total_flights"] == 1 and v["total_flight_hours"] == 1.0
    for url in (f"/api/batteries/{bid}/stats", f"/api/sensors/{sid}/stats", f"/api/attachments/{aid}/stats"):
        body = client.get(url, headers=admin_headers).json()
        assert body["total_flights"] == 1, url
        assert body["total_hours"] == 1.0, url


# ── A-F9: registration auto expiry is three calendar years ──────────────────

def test_registration_expiry_is_same_date_three_years_later(client, admin_headers):
    vid = _vehicle(client, admin_headers)["id"]
    cases = [("2023-01-01", "2026-01-01"), ("2025-06-01", "2028-06-01"),
             ("2024-02-29", "2027-02-28")]
    for reg_date, expected in cases:
        resp = client.post(f"/api/vehicles/{vid}/registrations", headers=admin_headers,
                           json={"registration_number": "FA0000TEST", "registration_date": reg_date})
        assert resp.status_code == 200, resp.text
        assert resp.json()["expiry_date"] == expected, reg_date


# ── A-F11: deleting the current registration promotes the latest one left ──

def _registration(client, headers, vid, number, reg_date):
    resp = client.post(f"/api/vehicles/{vid}/registrations", headers=headers,
                       json={"registration_number": number, "registration_date": reg_date})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _current(client, headers, vid):
    rows = client.get("/api/vehicle-registrations/current", headers=headers).json()
    return [r for r in rows if r["vehicle_id"] == vid]


def test_deleting_current_registration_promotes_latest_remaining(client, admin_headers):
    vid = _vehicle(client, admin_headers)["id"]
    _registration(client, admin_headers, vid, "REG-A", "2020-01-01")
    _registration(client, admin_headers, vid, "REG-C", "2024-01-01")
    _registration(client, admin_headers, vid, "REG-B", "2022-01-01")
    newest = _registration(client, admin_headers, vid, "REG-D", "2025-01-01")

    resp = client.delete(f"/api/vehicle-registrations/{newest['id']}", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    current = _current(client, admin_headers, vid)
    assert [r["registration_number"] for r in current] == ["REG-C"]


def test_deleting_an_old_registration_keeps_the_current_one(client, admin_headers):
    vid = _vehicle(client, admin_headers)["id"]
    old = _registration(client, admin_headers, vid, "REG-A", "2020-01-01")
    _registration(client, admin_headers, vid, "REG-B", "2019-01-01")
    client.delete(f"/api/vehicle-registrations/{old['id']}", headers=admin_headers)
    assert [r["registration_number"] for r in _current(client, admin_headers, vid)] == ["REG-B"]


# ── A-F15: a battery with readings can be deleted ───────────────────────────

def test_battery_with_readings_deletes_with_its_readings(client, db, admin_headers):
    from app.models.battery_reading import BatteryReading
    bid = client.post("/api/batteries", headers=admin_headers, json={"serial_number": "BAT-R1"}).json()["id"]
    other = client.post("/api/batteries", headers=admin_headers, json={"serial_number": "BAT-R2"}).json()["id"]
    for b in (bid, other):
        resp = client.post(f"/api/batteries/{b}/readings", headers=admin_headers, json={"health_pct": 70})
        assert resp.status_code == 200, resp.text

    resp = client.delete(f"/api/batteries/{bid}", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert client.get(f"/api/batteries/{bid}", headers=admin_headers).status_code == 404
    db.expire_all()
    assert db.query(BatteryReading).filter(BatteryReading.battery_id == bid).count() == 0
    assert db.query(BatteryReading).filter(BatteryReading.battery_id == other).count() == 1


# ── A-F21: an inactive schedule cannot be completed again ───────────────────

def _schedule(client, headers, vid, **extra):
    payload = {"name": "Prop check", "entity_type": "vehicle", "entity_id": vid,
               "frequency": "monthly", **extra}
    resp = client.post("/api/maintenance/schedules", headers=headers, json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def test_completed_one_time_schedule_cannot_be_completed_again(client, db, admin_headers):
    from app.models.maintenance import MaintenanceRecord
    vid = _vehicle(client, admin_headers)["id"]
    sid = _schedule(client, admin_headers, vid, frequency="one_time", next_due="2026-01-01")
    assert client.post(f"/api/maintenance/schedules/{sid}/complete", headers=admin_headers).status_code == 200
    again = client.post(f"/api/maintenance/schedules/{sid}/complete", headers=admin_headers)
    assert again.status_code == 400, again.text
    assert "already completed" in again.json()["detail"].lower()
    db.expire_all()
    assert db.query(MaintenanceRecord).count() == 1


# ── A-F41 / G-9: completing a schedule clears its overdue alert ─────────────

def _open_maintenance_alerts(db):
    from app.models.alert import Alert
    db.expire_all()
    return db.query(Alert).filter(Alert.type == "maintenance_due", Alert.is_dismissed.is_(False)).all()


def test_completing_a_schedule_dismisses_its_overdue_alert(client, db, admin_headers):
    from app.models.maintenance_schedule import MaintenanceSchedule
    from app.services.scheduler import check_maintenance_schedules
    vid = _vehicle(client, admin_headers)["id"]
    other = _vehicle(client, admin_headers, serial_number="VEH-002")["id"]
    sid = _schedule(client, admin_headers, vid, next_due="2026-01-01")
    _schedule(client, admin_headers, other, next_due="2026-01-01")
    check_maintenance_schedules(db)
    assert len(_open_maintenance_alerts(db)) == 2

    assert client.post(f"/api/maintenance/schedules/{sid}/complete", headers=admin_headers).status_code == 200
    assert [a.entity_id for a in _open_maintenance_alerts(db)] == [other]

    # Overdue again later: a fresh alert is raised, not blocked by the old one.
    db.query(MaintenanceSchedule).filter(MaintenanceSchedule.id == sid).update({"next_due": date(2026, 2, 1)})
    db.commit()
    check_maintenance_schedules(db)
    assert sorted(a.entity_id for a in _open_maintenance_alerts(db)) == sorted([vid, other])


def test_alert_check_dismisses_alerts_whose_schedule_is_no_longer_overdue(client, db, admin_headers):
    from app.models.alert import Alert
    from app.services.scheduler import check_maintenance_schedules
    vid = _vehicle(client, admin_headers)["id"]
    _schedule(client, admin_headers, vid, next_due="2099-01-01")
    db.add(Alert(type="maintenance_due", severity="warning", title="Maintenance Due: Prop check",
                 message="overdue (due 2026-01-01)", entity_type="vehicle", entity_id=vid))
    db.commit()
    check_maintenance_schedules(db)
    assert _open_maintenance_alerts(db) == []


# ── A-F37: equipment flight history returns what the detail pages read ──────

def test_equipment_flight_items_carry_vehicle_id_and_location(client, db, admin_headers):
    from app.models.pilot import Pilot
    vid = _vehicle(client, admin_headers)["id"]
    bid = client.post("/api/batteries", headers=admin_headers, json={"serial_number": "BAT-1"}).json()["id"]
    sid = client.post("/api/sensors", headers=admin_headers, json={"serial_number": "SEN-1"}).json()["id"]
    aid = client.post("/api/attachments", headers=admin_headers, json={"serial_number": "ATT-1"}).json()["id"]
    pilots = [Pilot(first_name="Ann", last_name="One", status="active"),
              Pilot(first_name="Bo", last_name="Two", status="active")]
    db.add_all(pilots)
    db.commit()
    gear = dict(battery_serial="BAT-1", sensor_package="SEN-1", attachment_top="ATT-1",
                attachment_left="ATT-1", takeoff_address="1 Test Field")
    _flight(db, vid, 600, pilot_id=pilots[0].id, **gear)
    _flight(db, vid, 600, pilot_id=pilots[1].id, **gear)
    _flight(db, vid, 600, pilot_id=pilots[1].id, **gear)

    for url in (f"/api/batteries/{bid}/flights", f"/api/sensors/{sid}/flights", f"/api/attachments/{aid}/flights"):
        item = client.get(url, headers=admin_headers).json()[0]
        assert item["vehicle_id"] == vid, url
        assert item["takeoff_address"] == "1 Test Field", url
    att = client.get(f"/api/attachments/{aid}/flights", headers=admin_headers).json()[0]
    assert att["positions"] == ["top", "left"]
    for url in (f"/api/sensors/{sid}/stats", f"/api/attachments/{aid}/stats"):
        assert client.get(url, headers=admin_headers).json()["unique_pilots"] == 2, url


# ── A-F2: status must be one the equipment type uses ────────────────────────

def test_vehicle_status_outside_the_list_is_refused(client, admin_headers):
    resp = client.post("/api/vehicles", headers=admin_headers, json={
        "serial_number": "VEH-S1", "manufacturer": "Acme", "model": "Hawk", "status": "banana"})
    assert resp.status_code == 422, resp.text
    assert "active" in resp.json()["detail"]
    vid = _vehicle(client, admin_headers)["id"]
    assert client.patch(f"/api/vehicles/{vid}", headers=admin_headers, json={"status": "banana"}).status_code == 422
    for status in ("maintenance", "damaged", "retired", "active"):
        resp = client.patch(f"/api/vehicles/{vid}", headers=admin_headers, json={"status": status})
        assert resp.status_code == 200, f"{status}: {resp.text}"


def test_each_equipment_type_takes_its_own_statuses(client, admin_headers):
    cases = [
        ("/api/batteries", {"serial_number": "B-S"}, "charging", "online"),
        ("/api/docks", {"serial_number": "D-S"}, "online", "charging"),
        ("/api/controllers", {"serial_number": "C-S"}, "damaged", "online"),
        ("/api/sensors", {"serial_number": "S-S"}, "maintenance", "charging"),
        ("/api/attachments", {"serial_number": "A-S"}, "retired", "banana"),
        ("/api/other-equipment", {"name": "Case"}, "damaged", "inactive"),
    ]
    for url, payload, good, bad in cases:
        assert client.post(url, headers=admin_headers, json={**payload, "status": bad}).status_code == 422, url
        resp = client.post(url, headers=admin_headers, json={**payload, "status": good})
        assert resp.status_code == 200, f"{url}: {resp.text}"


def test_a_stored_legacy_status_does_not_block_other_edits(client, db, admin_headers):
    from app.models.controller import Controller
    c = Controller(serial_number="C-OLD", status="inactive")
    db.add(c)
    db.commit()
    resp = client.patch(f"/api/controllers/{c.id}", headers=admin_headers,
                        json={"nickname": "Spare", "status": "inactive"})
    assert resp.status_code == 200, resp.text


# ── A-F3: decommissioned date cannot precede the acquired date ──────────────

def test_decommissioned_before_acquired_is_refused(client, admin_headers):
    dates = {"acquired_date": "2026-05-01", "decommissioned_date": "2025-01-01"}
    resp = client.post("/api/vehicles", headers=admin_headers, json={
        "serial_number": "VEH-D1", "manufacturer": "Acme", "model": "Hawk", **dates})
    assert resp.status_code == 422, resp.text
    for url, payload in [("/api/batteries", {"serial_number": "B-D"}), ("/api/docks", {"serial_number": "D-D"}),
                         ("/api/other-equipment", {"name": "Case"})]:
        assert client.post(url, headers=admin_headers, json={**payload, **dates}).status_code == 422, url

    # A patch is checked against the stored date too.
    vid = _vehicle(client, admin_headers, acquired_date="2026-05-01")["id"]
    resp = client.patch(f"/api/vehicles/{vid}", headers=admin_headers, json={"decommissioned_date": "2026-04-30"})
    assert resp.status_code == 422, resp.text
    resp = client.patch(f"/api/vehicles/{vid}", headers=admin_headers, json={"decommissioned_date": "2026-05-01"})
    assert resp.status_code == 200, resp.text


# ── A-F4: text longer than its column is refused ────────────────────────────

def test_fleet_text_longer_than_its_column_is_refused(client, admin_headers):
    resp = client.post("/api/vehicles", headers=admin_headers, json={
        "serial_number": "S" * 310, "manufacturer": "Acme", "model": "Hawk"})
    assert resp.status_code == 422, resp.text
    resp = client.post("/api/vehicles", headers=admin_headers, json={
        "serial_number": "VEH-L1", "manufacturer": "Acme", "model": "Hawk", "nickname": "N" * 101})
    assert resp.status_code == 422, resp.text
    assert "100" in str(resp.json()["detail"])
    resp = client.post("/api/batteries", headers=admin_headers, json={"serial_number": "B" * 101})
    assert resp.status_code == 422, resp.text
    resp = client.post("/api/docks", headers=admin_headers, json={"serial_number": "D-L", "name": "x" * 201})
    assert resp.status_code == 422, resp.text


# ── A-F5: specific errors instead of the generic 409 ────────────────────────

def test_vehicle_patch_to_duplicate_serial_says_so(client, admin_headers):
    _vehicle(client, admin_headers)
    vid = _vehicle(client, admin_headers, serial_number="VEH-002")["id"]
    resp = client.patch(f"/api/vehicles/{vid}", headers=admin_headers, json={"serial_number": "VEH-001"})
    assert resp.status_code == 400, resp.text
    assert "serial number already exists" in resp.json()["detail"]
    # Re-sending its own serial is fine.
    assert client.patch(f"/api/vehicles/{vid}", headers=admin_headers,
                        json={"serial_number": "VEH-002"}).status_code == 200


def test_vehicle_patch_null_required_field_is_422(client, admin_headers):
    vid = _vehicle(client, admin_headers)["id"]
    for field in ("serial_number", "manufacturer", "model", "status"):
        resp = client.patch(f"/api/vehicles/{vid}", headers=admin_headers, json={field: None})
        assert resp.status_code == 422, f"{field}: {resp.text}"


def test_registration_with_unknown_document_is_404(client, admin_headers):
    vid = _vehicle(client, admin_headers)["id"]
    resp = client.post(f"/api/vehicles/{vid}/registrations", headers=admin_headers,
                       json={"registration_number": "FA0000TEST", "document_id": 9999})
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "Document not found"


# ── A-F7: Vehicles CSV lifecycle columns and current registration ───────────

def test_vehicles_csv_has_lifecycle_dates_and_current_registration(client, admin_headers):
    import csv
    import io
    vid = _vehicle(client, admin_headers, faa_registration="LEGACY-1", acquired_date="2024-02-03",
                   decommissioned_date="2026-01-02")["id"]
    _vehicle(client, admin_headers, serial_number="VEH-002", faa_registration="LEGACY-2")
    _registration(client, admin_headers, vid, "FA-CURRENT", "2025-01-01")
    rows = list(csv.DictReader(io.StringIO(client.get("/api/export/vehicles/csv", headers=admin_headers).text)))
    by_serial = {r["Serial"]: r for r in rows}
    assert by_serial["VEH-001"]["Acquired"] == "2024-02-03"
    assert by_serial["VEH-001"]["Decommissioned"] == "2026-01-02"
    assert by_serial["VEH-001"]["FAA Reg"] == "FA-CURRENT"
    assert by_serial["VEH-002"]["FAA Reg"] == "LEGACY-2"
    assert by_serial["VEH-002"]["Acquired"] == ""


# ── A-F8: vehicle location place must be 1-100 characters ───────────────────

def test_vehicle_location_place_blank_or_long_is_refused(client, admin_headers):
    vid = _vehicle(client, admin_headers)["id"]
    for place in ("", "   ", "x" * 101):
        resp = client.patch(f"/api/vehicles/{vid}/location", headers=admin_headers, json={"place": place})
        assert resp.status_code == 422, f"{place!r}: {resp.text}"
    resp = client.patch(f"/api/vehicles/{vid}/location", headers=admin_headers, json={"place": " Hangar 2 "})
    assert resp.status_code == 200, resp.text
    row = next(r for r in client.get("/api/vehicles/locations", headers=admin_headers).json() if r["vehicle_id"] == vid)
    assert row["location_text"] == "Hangar 2"


# ── A-F10: registration needs a number or date; expiry after registration ───

def test_registration_validation(client, admin_headers):
    vid = _vehicle(client, admin_headers)["id"]
    url = f"/api/vehicles/{vid}/registrations"
    for body in ({}, {"registration_number": "  ", "notes": "x"},
                 {"registration_date": "2025-01-01", "expiry_date": "2024-12-31"},
                 {"registration_number": "R" * 101}):
        resp = client.post(url, headers=admin_headers, json=body)
        assert resp.status_code == 422, f"{body}: {resp.text}"
    assert _current(client, admin_headers, vid) == []
    assert client.post(url, headers=admin_headers, json={"registration_date": "2025-01-01"}).status_code == 200
    assert client.post(url, headers=admin_headers, json={"registration_number": "FA-1"}).status_code == 200



# ── A-F16: battery reading validation ───────────────────────────────────────

def test_battery_reading_validation(client, admin_headers):
    bid = client.post("/api/batteries", headers=admin_headers,
                      json={"serial_number": "BAT-V", "cycle_count": 30}).json()["id"]
    url = f"/api/batteries/{bid}/readings"
    for body in ({}, {"notes": "only a note"}, {"voltage": -1}, {"capacity_mah": -5},
                 {"temperature_c": -500}, {"temperature_c": 600}, {"health_pct": 80, "notes": "n" * 501}):
        resp = client.post(url, headers=admin_headers, json=body)
        assert resp.status_code == 422, f"{body}: {resp.text}"
    resp = client.post(url, headers=admin_headers, json={"cycle_count": 5})
    assert resp.status_code == 422, resp.text
    assert "30" in resp.json()["detail"]
    assert client.get(f"/api/batteries/{bid}", headers=admin_headers).json()["cycle_count"] == 30
    assert client.get(f"/api/batteries/{bid}/health-history", headers=admin_headers).json() == []

    resp = client.post(url, headers=admin_headers, json={"cycle_count": 31, "voltage": 15.2, "temperature_c": -10})
    assert resp.status_code == 200, resp.text


# ── A-F17: controller stats carry no made-up flight figures ─────────────────

def test_controller_stats_do_not_report_fake_zero_flights(client, admin_headers):
    cid = client.post("/api/controllers", headers=admin_headers, json={"serial_number": "C-1"}).json()["id"]
    body = client.get(f"/api/controllers/{cid}/stats", headers=admin_headers).json()
    assert "total_flights" not in body and "total_hours" not in body
    assert body["assigned_pilot"] is None


# ── A-F18: dock coordinates in range ────────────────────────────────────────

def test_dock_coordinates_out_of_range_are_refused(client, admin_headers):
    for body in ({"lat": 200}, {"lon": -500}, {"lat": -90.1}, {"lon": 180.5}):
        resp = client.post("/api/docks", headers=admin_headers, json={"serial_number": "D-1", **body})
        assert resp.status_code == 422, f"{body}: {resp.text}"
    did = client.post("/api/docks", headers=admin_headers,
                      json={"serial_number": "D-1", "lat": -90, "lon": 180}).json()["id"]
    assert client.patch(f"/api/docks/{did}", headers=admin_headers, json={"lat": 91}).status_code == 422


# ── A-F19: maintenance record validation ────────────────────────────────────

def test_maintenance_record_validation(client, admin_headers):
    vid = _vehicle(client, admin_headers)["id"]
    base = {"entity_type": "vehicle", "entity_id": vid, "description": "Prop swap"}
    for extra in ({"description": ""}, {"description": "   "}, {"cost": -50}, {"next_due_hours": -1},
                  {"maintenance_type": "zzz"},
                  {"performed_date": "2026-03-01", "next_due_date": "2026-02-01"}):
        resp = client.post("/api/maintenance", headers=admin_headers, json={**base, **extra})
        assert resp.status_code == 422, f"{extra}: {resp.text}"
    rid = client.post("/api/maintenance", headers=admin_headers,
                      json={**base, "performed_date": "2026-03-01", "cost": 0}).json()["id"]
    for extra in ({"next_due_date": "2026-02-28"}, {"cost": -1}, {"description": ""}, {"maintenance_type": "zzz"}):
        resp = client.patch(f"/api/maintenance/{rid}", headers=admin_headers, json=extra)
        assert resp.status_code == 422, f"{extra}: {resp.text}"
    assert client.patch(f"/api/maintenance/{rid}", headers=admin_headers,
                        json={"next_due_date": "2026-04-01", "maintenance_type": "inspection"}).status_code == 200


# ── A-F20: schedule name and entity_id ──────────────────────────────────────

def test_schedule_needs_a_name_and_an_entity_for_table_types(client, admin_headers):
    vid = _vehicle(client, admin_headers)["id"]
    url = "/api/maintenance/schedules"
    for name in ("", "   "):
        resp = client.post(url, headers=admin_headers, json={
            "name": name, "entity_type": "vehicle", "entity_id": vid, "frequency": "monthly"})
        assert resp.status_code == 422, resp.text
    resp = client.post(url, headers=admin_headers, json={"name": "x", "entity_type": "vehicle", "frequency": "monthly"})
    assert resp.status_code == 400, resp.text
    assert "entity_id is required" in resp.json()["detail"]
    sid = _schedule(client, admin_headers, vid)
    assert client.patch(f"{url}/{sid}", headers=admin_headers, json={"entity_id": None}).status_code == 400
    assert client.patch(f"{url}/{sid}", headers=admin_headers, json={"name": " "}).status_code == 422
    # Org-wide and other tasks still take no entity.
    for etype in ("organization", "other"):
        resp = client.post(url, headers=admin_headers, json={"name": "x", "entity_type": etype, "frequency": "monthly"})
        assert resp.status_code == 200, f"{etype}: {resp.text}"


# ── A-F24: checkout validation ──────────────────────────────────────────────

def _pilot(db):
    from app.models.pilot import Pilot
    p = Pilot(first_name="Test", last_name="Pilot", status="active")
    db.add(p)
    db.commit()
    return p.id


def test_retired_or_damaged_equipment_cannot_be_checked_out(client, db, admin_headers):
    pid = _pilot(db)
    for status in ("retired", "damaged"):
        cid = client.post("/api/controllers", headers=admin_headers,
                          json={"serial_number": f"C-{status}", "status": status}).json()["id"]
        resp = client.post("/api/equipment-checkouts", headers=admin_headers, json={
            "entity_type": "controller", "entity_id": cid, "checked_out_by_id": pid})
        assert resp.status_code == 400, resp.text
        assert "cannot be checked out" in resp.json()["detail"]


def test_checkout_condition_must_be_a_known_value(client, db, admin_headers):
    pid = _pilot(db)
    vid = _vehicle(client, admin_headers)["id"]
    body = {"entity_type": "vehicle", "entity_id": vid, "checked_out_by_id": pid}
    resp = client.post("/api/equipment-checkouts", headers=admin_headers, json={**body, "condition_out": "exploded"})
    assert resp.status_code == 422, resp.text
    co = client.post("/api/equipment-checkouts", headers=admin_headers, json={**body, "condition_out": "fair"})
    assert co.status_code == 200, co.text
    resp = client.post(f"/api/equipment-checkouts/{co.json()['id']}/checkin", headers=admin_headers,
                       json={"checked_in_by_id": pid, "condition_in": "broken"})
    assert resp.status_code == 422, resp.text


def test_checkout_expected_return_carries_the_display_zone(client, db, admin_headers):
    from app.models.setting import Setting
    db.add(Setting(key="display_timezone", value="America/Chicago"))
    db.commit()
    pid = _pilot(db)
    vid = _vehicle(client, admin_headers)["id"]
    co = client.post("/api/equipment-checkouts", headers=admin_headers, json={
        "entity_type": "vehicle", "entity_id": vid, "checked_out_by_id": pid,
        "expected_return": "2026-11-10"}).json()
    assert co["expected_return"] == "2026-11-10T00:00:00-06:00"
    assert co["checked_out_at"].endswith("+00:00")
    client.post(f"/api/equipment-checkouts/{co['id']}/checkin", headers=admin_headers, json={"checked_in_by_id": pid})
    # An aware value is turned into the same wall-clock zone.
    co = client.post("/api/equipment-checkouts", headers=admin_headers, json={
        "entity_type": "vehicle", "entity_id": vid, "checked_out_by_id": pid,
        "expected_return": "2026-11-10T18:00:00Z"}).json()
    assert co["expected_return"] == "2026-11-10T12:00:00-06:00"
