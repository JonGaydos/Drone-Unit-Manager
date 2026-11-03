"""Fleet, pilot, certification and picker routes enforce the role permission grid."""

from datetime import date

import pytest

from app.models.attachment import Attachment
from app.models.battery import Battery
from app.models.component import Component
from app.models.flight import Flight
from app.models.folder import Folder
from app.models.pilot import Pilot
from app.models.sensor import SensorPackage
from app.models.vehicle import Vehicle
from app.services.permissions import REGISTRY

PERMISSIONS_URL = "/api/permissions"
COMPONENTS_URL = "/api/components"
VEHICLES_URL = "/api/vehicles"
PILOTS_URL = "/api/pilots"
PILOT_OPTIONS_URL = "/api/pilots/options"
FLEET_OPTIONS_URL = "/api/fleet/options"
FOLDERS_URL = "/api/folders"
AUDIT_URL = "/api/audit"
AUDIT_CSV_URL = "/api/export/audit/csv"
REGISTRATIONS_URL = "/api/vehicle-registrations/current"
CERT_TYPES_URL = "/api/certification-types"
SEARCH_URL = "/api/search?q=secret"
FLIGHTS_CSV_URL = "/api/export/flights/csv"
SECRET_EMAIL = "secret.pilot@example.com"
PILOTS_CONTACTS = "pilots.contacts"
PILOTS_VIEW = "pilots.view"
PILOTS_EDIT = "pilots.edit"
PILOTS_MANAGE = "pilots.manage"
FLEET_VIEW = "fleet.view"
FLEET_MANAGE = "fleet.manage"
FILES_VIEW = "files.view"
COMPONENT_BODY = {"name": "Gimbal", "component_type": "gimbal"}


def _grid(client, headers, *changes):
    body = {"changes": [{"role": r, "key": k, "value": v} for r, k, v in changes]}
    resp = client.put(PERMISSIONS_URL, headers=headers, json=body)
    assert resp.status_code == 200, resp.text


def _view_off(client, admin_headers, role, view_key):
    """Turn a view key off for a role, along with every key that requires it."""
    changes = [
        (role, key, "none" if definition.kind == "level" else "no")
        for key, definition in REGISTRY.items()
        if definition.requires == view_key
    ]
    changes.append((role, view_key, "no"))
    _grid(client, admin_headers, *changes)


def _vehicle(db):
    vehicle = Vehicle(serial_number="V-1", manufacturer="Skydio", model="X10")
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    return vehicle


def _component(db):
    component = Component(name="Gimbal", component_type="gimbal")
    db.add(component)
    db.commit()
    db.refresh(component)
    return component


def _other_pilot(db, email=SECRET_EMAIL):
    pilot = Pilot(first_name="Other", last_name="Pilot", email=email, phone="555-0100")
    db.add(pilot)
    db.commit()
    db.refresh(pilot)
    return pilot


def test_pilot_cannot_manage_components(client, db, pilot_headers):
    component = _component(db)
    url = f"{COMPONENTS_URL}/{component.id}"
    assert client.post(COMPONENTS_URL, headers=pilot_headers, json=COMPONENT_BODY).status_code == 403
    assert client.patch(url, headers=pilot_headers, json={"notes": "x"}).status_code == 403
    assert client.delete(url, headers=pilot_headers).status_code == 403
    assert client.get(url, headers=pilot_headers).status_code == 200


def test_supervisor_can_manage_components(client, db, supervisor_headers):
    resp = client.post(COMPONENTS_URL, headers=supervisor_headers, json=COMPONENT_BODY)
    assert resp.status_code == 201
    url = f"{COMPONENTS_URL}/{resp.json()['id']}"
    assert client.patch(url, headers=supervisor_headers, json={"notes": "x"}).status_code == 200
    assert client.delete(url, headers=supervisor_headers).status_code == 200


def test_fleet_manage_grantable_to_pilot(client, db, admin_headers, pilot_headers):
    _grid(client, admin_headers, ("pilot", FLEET_MANAGE, "yes"))
    assert client.post(COMPONENTS_URL, headers=pilot_headers, json=COMPONENT_BODY).status_code == 201
    body = {"serial_number": "B-1"}
    assert client.post("/api/batteries", headers=pilot_headers, json=body).status_code == 200


def test_pilot_can_set_vehicle_location(client, db, admin_headers, pilot_headers, viewer_headers):
    vehicle = _vehicle(db)
    url = f"{VEHICLES_URL}/{vehicle.id}/location"
    assert client.patch(url, headers=pilot_headers, json={"place": "Hangar"}).status_code == 200
    assert client.patch(url, headers=viewer_headers, json={"place": "Hangar"}).status_code == 403
    _grid(client, admin_headers, ("pilot", "fleet.location", "no"))
    assert client.patch(url, headers=pilot_headers, json={"place": "Truck"}).status_code == 403


def test_pilot_cannot_edit_vehicle(client, db, supervisor_headers, pilot_headers):
    vehicle = _vehicle(db)
    url = f"{VEHICLES_URL}/{vehicle.id}"
    assert client.patch(url, headers=pilot_headers, json={"notes": "x"}).status_code == 403
    assert client.patch(url, headers=supervisor_headers, json={"notes": "x"}).status_code == 200


def test_pilot_edits_only_own_profile(client, db, admin_headers, pilot_headers, linked_pilot):
    other = _other_pilot(db)
    assert client.patch(f"{PILOTS_URL}/{linked_pilot.id}", headers=pilot_headers, json={"notes": "mine"}).status_code == 200
    assert client.patch(f"{PILOTS_URL}/{other.id}", headers=pilot_headers, json={"notes": "theirs"}).status_code == 403
    _grid(client, admin_headers, ("pilot", PILOTS_EDIT, "all"))
    assert client.patch(f"{PILOTS_URL}/{other.id}", headers=pilot_headers, json={"notes": "theirs"}).status_code == 200


def test_unlinked_pilot_user_edits_no_profile(client, db, pilot_headers, pilot_user):
    other = _other_pilot(db)
    assert pilot_user.pilot_id is None
    assert client.patch(f"{PILOTS_URL}/{other.id}", headers=pilot_headers, json={"notes": "x"}).status_code == 403


def test_pilot_cannot_set_supervisor_only_fields(client, db, admin_headers, pilot_headers, linked_pilot):
    url = f"{PILOTS_URL}/{linked_pilot.id}"
    assert client.patch(url, headers=pilot_headers, json={"status": "inactive"}).status_code == 403
    assert client.patch(url, headers=pilot_headers, json={"counts_toward_totals": False}).status_code == 403
    assert client.patch(url, headers=pilot_headers, json={"status": linked_pilot.status}).status_code == 200
    _grid(client, admin_headers, ("pilot", PILOTS_MANAGE, "yes"))
    assert client.patch(url, headers=pilot_headers, json={"status": "inactive"}).status_code == 200


def test_supervisor_pilot_manage_and_grant(client, db, admin_headers, supervisor_headers, pilot_headers):
    body = {"first_name": "New", "last_name": "Pilot"}
    assert client.post(PILOTS_URL, headers=pilot_headers, json=body).status_code == 403
    created = client.post(PILOTS_URL, headers=supervisor_headers, json=body)
    assert created.status_code == 200
    _grid(client, admin_headers, ("supervisor", PILOTS_MANAGE, "no"))
    assert client.post(PILOTS_URL, headers=supervisor_headers, json=body).status_code == 403
    assert client.delete(f"{PILOTS_URL}/{created.json()['id']}", headers=supervisor_headers).status_code == 403


def test_contacts_toggle(client, db, admin_headers, viewer_headers):
    pilot = _other_pilot(db)
    db.add(Flight(date=date(2026, 3, 1), pilot_id=pilot.id, external_id="F-1"))
    db.commit()

    def seen():
        listing = client.get(PILOTS_URL, headers=viewer_headers).json()[0]
        detail = client.get(f"{PILOTS_URL}/{pilot.id}", headers=viewer_headers).json()
        found = client.get(SEARCH_URL, headers=viewer_headers).json()["results"]
        csv_text = client.get(FLIGHTS_CSV_URL, headers=viewer_headers).text
        return listing["email"], detail["email"], len(found), SECRET_EMAIL in csv_text

    assert seen() == (None, None, 0, False)
    _grid(client, admin_headers, ("viewer", PILOTS_CONTACTS, "yes"))
    assert seen() == (SECRET_EMAIL, SECRET_EMAIL, 1, True)


def test_contacts_follow_pilot_role(client, db, admin_headers, pilot_headers):
    pilot = _other_pilot(db)
    assert client.get(f"{PILOTS_URL}/{pilot.id}", headers=pilot_headers).json()["email"] == SECRET_EMAIL
    _grid(client, admin_headers, ("pilot", PILOTS_CONTACTS, "no"))
    assert client.get(f"{PILOTS_URL}/{pilot.id}", headers=pilot_headers).json()["email"] is None


def test_options_available_with_view_off(client, db, admin_headers, pilot_headers):
    _other_pilot(db)
    _vehicle(db)
    _view_off(client, admin_headers, "pilot", PILOTS_VIEW)
    _view_off(client, admin_headers, "pilot", FLEET_VIEW)
    assert client.get(PILOTS_URL, headers=pilot_headers).status_code == 403
    assert client.get(VEHICLES_URL, headers=pilot_headers).status_code == 403
    pilots = client.get(PILOT_OPTIONS_URL, headers=pilot_headers)
    assert pilots.status_code == 200
    assert set(pilots.json()[0]) == {"id", "full_name", "badge_number", "status"}
    assert SECRET_EMAIL not in pilots.text
    fleet = client.get(FLEET_OPTIONS_URL, headers=pilot_headers)
    assert fleet.status_code == 200
    body = fleet.json()
    assert set(body) == {"vehicles", "batteries", "controllers", "sensors", "attachments", "docks", "other_equipment"}
    assert set(body["vehicles"][0]) == {"id", "name", "status", "nickname", "manufacturer", "model", "serial_number"}


def test_fleet_options_carry_the_serial_a_flight_form_stores(client, db, viewer_headers):
    db.add_all([
        Battery(serial_number="BAT-1", nickname="Blue"),
        SensorPackage(serial_number="SEN-1", name="Thermal"),
        Attachment(serial_number="ATT-1", name="Spotlight"),
    ])
    db.commit()
    body = client.get(FLEET_OPTIONS_URL, headers=viewer_headers).json()
    assert body["batteries"][0]["serial_number"] == "BAT-1"
    assert body["batteries"][0]["name"] == "Blue"
    assert body["sensors"][0]["serial_number"] == "SEN-1"
    assert body["attachments"][0]["serial_number"] == "ATT-1"


def test_options_need_sign_in(client):
    assert client.get(PILOT_OPTIONS_URL).status_code == 401
    assert client.get(FLEET_OPTIONS_URL).status_code == 401


def test_options_sorted_with_inactive(client, db, viewer_headers):
    db.add_all([
        Pilot(first_name="Zed", last_name="Last", status="inactive"),
        Pilot(first_name="Amy", last_name="First"),
    ])
    db.commit()
    rows = client.get(PILOT_OPTIONS_URL, headers=viewer_headers).json()
    assert [r["full_name"] for r in rows] == ["Amy First", "Zed Last"]
    assert [r["status"] for r in rows] == ["active", "inactive"]


@pytest.mark.parametrize("view_key,url", [
    (FLEET_VIEW, "/api/batteries"),
    (FLEET_VIEW, "/api/controllers"),
    (FLEET_VIEW, "/api/docks"),
    (FLEET_VIEW, "/api/sensors"),
    (FLEET_VIEW, "/api/attachments"),
    (FLEET_VIEW, "/api/other-equipment"),
    (FLEET_VIEW, COMPONENTS_URL),
    (FLEET_VIEW, VEHICLES_URL),
    (FLEET_VIEW, VEHICLES_URL + "/locations"),
    (PILOTS_VIEW, PILOTS_URL),
    ("certifications.view", CERT_TYPES_URL),
    ("certifications.view", "/api/pilot-certifications"),
    ("certifications.view", "/api/pilot-equipment-quals"),
    ("certifications.view", "/api/certifications/matrix"),
    ("certifications.view", "/api/currency/rules"),
    ("certifications.view", "/api/currency/status"),
    ("authority.view", "/api/operating-authorities"),
    ("authority.view", "/api/geofences"),
    ("registrations.view", REGISTRATIONS_URL),
    (FILES_VIEW, FOLDERS_URL),
])
def test_view_off_hides_each_feature(client, admin_headers, pilot_headers, view_key, url):
    assert client.get(url, headers=pilot_headers).status_code == 200
    _view_off(client, admin_headers, "pilot", view_key)
    assert client.get(url, headers=pilot_headers).status_code == 403


def test_view_off_hides_detail_and_photo_routes(client, db, admin_headers, pilot_headers):
    vehicle = _vehicle(db)
    pilot = _other_pilot(db)
    _view_off(client, admin_headers, "pilot", FLEET_VIEW)
    _view_off(client, admin_headers, "pilot", PILOTS_VIEW)
    assert client.get(f"{VEHICLES_URL}/{vehicle.id}", headers=pilot_headers).status_code == 403
    assert client.get(f"{VEHICLES_URL}/{vehicle.id}/photo/view", headers=pilot_headers).status_code == 403
    assert client.get(f"{PILOTS_URL}/{pilot.id}", headers=pilot_headers).status_code == 403
    assert client.get(f"{PILOTS_URL}/{pilot.id}/photo/view", headers=pilot_headers).status_code == 403
    assert client.get(f"{PILOTS_URL}/{pilot.id}/stats", headers=pilot_headers).status_code == 403


def test_registrations_manage_off_for_supervisor_by_default(client, db, admin_headers, supervisor_headers):
    vehicle = _vehicle(db)
    url = f"{VEHICLES_URL}/{vehicle.id}/registrations"
    assert client.get(url, headers=supervisor_headers).status_code == 200
    assert client.post(url, headers=supervisor_headers, json={"registration_number": "R1"}).status_code == 403
    assert client.post(url, headers=admin_headers, json={"registration_number": "R1"}).status_code == 200


def test_registrations_manage_grantable(client, db, admin_headers, supervisor_headers):
    vehicle = _vehicle(db)
    _grid(client, admin_headers, ("supervisor", "registrations.manage", "yes"))
    url = f"{VEHICLES_URL}/{vehicle.id}/registrations"
    created = client.post(url, headers=supervisor_headers, json={"registration_number": "R1"})
    assert created.status_code == 200
    assert client.delete(f"/api/vehicle-registrations/{created.json()['id']}", headers=supervisor_headers).status_code == 200


@pytest.mark.parametrize("key,method,url,body", [
    ("certifications.manage", "post", CERT_TYPES_URL, {"name": "Part 107"}),
    ("authority.manage", "post", "/api/operating-authorities", {}),
    ("authority.manage", "post", "/api/geofences", {}),
    ("certifications.manage", "post", "/api/currency/rules", {}),
])
def test_manage_keys_grantable(client, admin_headers, pilot_headers, supervisor_headers, key, method, url, body):
    assert getattr(client, method)(url, headers=pilot_headers, json=body).status_code == 403
    _grid(client, admin_headers, ("supervisor", key, "no"))
    assert getattr(client, method)(url, headers=supervisor_headers, json=body).status_code == 403
    _grid(client, admin_headers, ("pilot", key, "yes"))
    assert getattr(client, method)(url, headers=pilot_headers, json=body).status_code != 403


def test_audit_view_grantable(client, admin_headers, supervisor_headers, pilot_headers):
    assert client.get(AUDIT_URL, headers=supervisor_headers).status_code == 403
    assert client.get(AUDIT_CSV_URL, headers=supervisor_headers).status_code == 403
    _grid(client, admin_headers, ("supervisor", "audit.view", "yes"))
    assert client.get(AUDIT_URL, headers=supervisor_headers).status_code == 200
    assert client.get(AUDIT_CSV_URL, headers=supervisor_headers).status_code == 200
    assert client.get(AUDIT_URL, headers=pilot_headers).status_code == 403
    assert client.get(AUDIT_CSV_URL, headers=pilot_headers).status_code == 403
    # The audit CSV also needs the export permission.
    _grid(client, admin_headers, ("supervisor", "reports.export", "no"))
    assert client.get(AUDIT_URL, headers=supervisor_headers).status_code == 200
    assert client.get(AUDIT_CSV_URL, headers=supervisor_headers).status_code == 403


def test_folder_manage_refused_for_pilot(client, db, admin_headers, supervisor_headers, pilot_headers):
    folder = Folder(name="Existing")
    db.add(folder)
    db.commit()
    url = f"{FOLDERS_URL}/{folder.id}"
    assert client.post(FOLDERS_URL, headers=pilot_headers, json={"name": "New"}).status_code == 403
    assert client.patch(url, headers=pilot_headers, json={"name": "Renamed"}).status_code == 403
    assert client.delete(url, headers=pilot_headers).status_code == 403
    assert client.post(FOLDERS_URL, headers=supervisor_headers, json={"name": "New"}).status_code == 200
    _grid(client, admin_headers, ("pilot", "folders.manage", "yes"))
    assert client.post(FOLDERS_URL, headers=pilot_headers, json={"name": "Mine"}).status_code == 200
