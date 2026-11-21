"""Flight operating cost estimated from the aircraft's hourly rate.

A cost typed on the flight always wins. Otherwise the flight carries an
estimate of duration hours x the vehicle's hourly rate, rounded to cents and
worked out when read (never stored). No rate, no vehicle or no duration means
no estimate.
"""

from datetime import date

from app.models.flight import Flight
from app.models.pilot import Pilot
from app.models.vehicle import Vehicle

GENERATE_URL = "/api/reports/generate"


def _vehicle(db, serial="SN-COST", rate=None, nickname="Cost Bird"):
    vehicle = Vehicle(serial_number=serial, manufacturer="Skydio", model="X2E",
                      nickname=nickname, status="active", hourly_operating_cost=rate)
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    return vehicle


def _flight(db, vehicle_id, duration_seconds, cost=None):
    pilot = db.query(Pilot).first()
    if pilot is None:
        pilot = Pilot(first_name="Ana", last_name="Alvarez", status="active")
        db.add(pilot)
        db.commit()
    flight = Flight(date=date(2025, 6, 1), pilot_id=pilot.id, vehicle_id=vehicle_id,
                    duration_seconds=duration_seconds, operating_cost=cost)
    db.add(flight)
    db.commit()
    db.refresh(flight)
    return flight


def _get_flight(client, headers, flight_id):
    resp = client.get(f"/api/flights/{flight_id}", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_estimate_is_hours_times_rate_rounded_to_cents(client, db, admin_headers):
    vehicle = _vehicle(db, rate=37.5)
    flight = _flight(db, vehicle.id, 1000)  # 0.2777... h x 37.5 = 10.4166...

    body = _get_flight(client, admin_headers, flight.id)

    assert body["operating_cost_estimate"] == 10.42


def test_estimate_leaves_the_typed_cost_empty(client, db, admin_headers):
    vehicle = _vehicle(db, rate=60)
    flight = _flight(db, vehicle.id, 3600)

    body = _get_flight(client, admin_headers, flight.id)

    assert body["operating_cost"] is None


def test_estimate_is_not_stored(client, db, admin_headers):
    vehicle = _vehicle(db, rate=60)
    flight = _flight(db, vehicle.id, 3600)
    _get_flight(client, admin_headers, flight.id)

    db.expire_all()
    assert db.get(Flight, flight.id).operating_cost is None


def test_typed_cost_wins_over_the_estimate(client, db, admin_headers):
    vehicle = _vehicle(db, rate=60)
    flight = _flight(db, vehicle.id, 3600, cost=12.0)

    body = _get_flight(client, admin_headers, flight.id)

    assert body["operating_cost"] == 12.0
    assert body["operating_cost_estimate"] is None


def test_no_rate_means_no_estimate(client, db, admin_headers):
    vehicle = _vehicle(db, rate=None)
    flight = _flight(db, vehicle.id, 3600)

    assert _get_flight(client, admin_headers, flight.id)["operating_cost_estimate"] is None


def test_no_vehicle_means_no_estimate(client, db, admin_headers):
    flight = _flight(db, None, 3600)

    assert _get_flight(client, admin_headers, flight.id)["operating_cost_estimate"] is None


def test_no_duration_means_no_estimate(client, db, admin_headers):
    vehicle = _vehicle(db, rate=60)
    flight = _flight(db, vehicle.id, None)

    assert _get_flight(client, admin_headers, flight.id)["operating_cost_estimate"] is None


def test_a_changed_rate_changes_past_estimates(client, db, admin_headers):
    vehicle = _vehicle(db, rate=60)
    flight = _flight(db, vehicle.id, 1800)
    vehicle.hourly_operating_cost = 100
    db.commit()

    assert _get_flight(client, admin_headers, flight.id)["operating_cost_estimate"] == 50.0


def test_flight_list_carries_the_estimate(client, db, admin_headers):
    vehicle = _vehicle(db, rate=40)
    _flight(db, vehicle.id, 5400)

    resp = client.get("/api/flights", headers=admin_headers)

    assert resp.status_code == 200, resp.text
    assert resp.json()["flights"][0]["operating_cost_estimate"] == 60.0


# Vehicle rate: field, validation, permission


def _vehicle_payload(**extra):
    return {"serial_number": "SN-NEW", "manufacturer": "Skydio", "model": "X10", **extra}


def test_vehicle_create_stores_the_rate(client, db, admin_headers):
    resp = client.post("/api/vehicles", headers=admin_headers, json=_vehicle_payload(hourly_operating_cost=85.5))

    assert resp.status_code == 200, resp.text
    assert resp.json()["hourly_operating_cost"] == 85.5


def test_vehicle_update_sets_and_clears_the_rate(client, db, admin_headers):
    vehicle = _vehicle(db, rate=10)
    url = f"/api/vehicles/{vehicle.id}"

    set_resp = client.patch(url, headers=admin_headers, json={"hourly_operating_cost": 22.25})
    clear_resp = client.patch(url, headers=admin_headers, json={"hourly_operating_cost": None})

    assert set_resp.json()["hourly_operating_cost"] == 22.25
    assert clear_resp.json()["hourly_operating_cost"] is None


def test_vehicle_rate_cannot_be_negative(client, db, admin_headers):
    vehicle = _vehicle(db)

    resp = client.patch(f"/api/vehicles/{vehicle.id}", headers=admin_headers, json={"hourly_operating_cost": -1})

    assert resp.status_code == 422


def test_vehicle_rate_has_a_ceiling(client, db, admin_headers):
    resp = client.post("/api/vehicles", headers=admin_headers, json=_vehicle_payload(hourly_operating_cost=100001))

    assert resp.status_code == 422


def test_setting_the_rate_needs_fleet_manage(client, db, pilot_headers):
    vehicle = _vehicle(db)

    resp = client.patch(f"/api/vehicles/{vehicle.id}", headers=pilot_headers, json={"hourly_operating_cost": 5})

    assert resp.status_code == 403


# Reports


def _generate(client, headers, report_type):
    resp = client.post(GENERATE_URL, headers=headers, json={"report_type": report_type})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _two_flights(db):
    """One flight with a typed 12.00, one estimated at 60/h x 0.5 h = 30.00."""
    vehicle = _vehicle(db, rate=60)
    _flight(db, vehicle.id, 3600, cost=12.0)
    _flight(db, vehicle.id, 1800)
    return vehicle


def test_flight_summary_totals_include_estimates(client, db, admin_headers):
    _two_flights(db)

    payload = _generate(client, admin_headers, "flight_summary")

    assert payload["summary"]["total_cost"] == "42.00"


def test_flight_summary_marks_estimated_rows(client, db, admin_headers):
    _two_flights(db)

    payload = _generate(client, admin_headers, "flight_summary")

    assert sorted(r["cost"] for r in payload["rows"]) == ["12.00", "30.00 (est.)"]


def test_flight_summary_says_the_total_includes_estimates(client, db, admin_headers):
    _two_flights(db)

    payload = _generate(client, admin_headers, "flight_summary")

    assert payload["summary"]["estimated_cost_flights"] == 1


def test_flight_summary_cost_is_blank_without_rate_or_typed_cost(client, db, admin_headers):
    vehicle = _vehicle(db, rate=None)
    _flight(db, vehicle.id, 3600)

    payload = _generate(client, admin_headers, "flight_summary")

    assert payload["rows"][0]["cost"] == ""


def test_equipment_utilization_totals_cost_per_aircraft(client, db, admin_headers):
    _two_flights(db)

    payload = _generate(client, admin_headers, "equipment_utilization")

    assert payload["rows"][0]["cost"] == "42.00"


def test_equipment_utilization_total_cost(client, db, admin_headers):
    _two_flights(db)
    other = _vehicle(db, serial="SN-OTHER", rate=10, nickname="Other")
    _flight(db, other.id, 3600)

    payload = _generate(client, admin_headers, "equipment_utilization")

    assert payload["summary"]["total_cost"] == "52.00"


def test_vehicles_csv_carries_the_rate(client, db, admin_headers):
    import csv
    import io
    _vehicle(db, rate=42.5)

    resp = client.get("/api/export/vehicles/csv", headers=admin_headers)

    row = next(csv.DictReader(io.StringIO(resp.text)))
    assert row["Hourly Operating Cost"] == "42.50"
