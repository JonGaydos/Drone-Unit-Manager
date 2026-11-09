"""Fleet and maintenance fixes from the 2026-11-08 staging test (Area 3)."""


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
