"""The audit log page and CSV show who acted, by login name, and every change.

Entries carry several ``changes`` shapes: field pairs, plain strings, and the
bulk and machine summaries with ``records``, ``deleted`` and counts. Each
output has to render all of them and hide contact values on every one.
"""

import csv
import io
from datetime import datetime

import pytest

from app.models.audit_log import AuditLog
from app.services.pilot_contacts import CONTACT_HIDDEN, redact_audit_changes

AUDIT_URL = "/api/audit"
CSV_URL = "/api/export/audit/csv"
EMAIL = "jane.doe@example.org"
PHONE = "555-0142"


def _rows(resp):
    assert resp.status_code == 200, resp.text
    return list(csv.reader(io.StringIO(resp.text)))


def _entry(db, **kw):
    values = {"user_name": "Jane", "action": "update", "entity_type": "pilot"}
    db.add(AuditLog(**{**values, **kw}))
    db.commit()


def _hide_contacts(client, admin_headers):
    changes = [{"role": "pilot", "key": key, "value": value}
               for key, value in (("audit.view", "yes"), ("reports.export", "yes"), ("pilots.contacts", "no"))]
    resp = client.put("/api/permissions", headers=admin_headers, json={"changes": changes})
    assert resp.status_code == 200, resp.text


def test_entry_returns_username_and_imported(client, db, admin_headers):
    _entry(db, user_username="jdoe", imported=True)
    _entry(db, user_name="Old", action="create")

    logs = {e["user_name"]: e for e in client.get(AUDIT_URL, headers=admin_headers).json()["logs"]}

    assert logs["Jane"]["user_username"] == "jdoe"
    assert logs["Jane"]["imported"] is True
    assert logs["Old"]["user_username"] is None
    assert logs["Old"]["imported"] is False


def test_entry_returns_the_client_ip_address(client, db, admin_headers):
    _entry(db, ip_address="10.0.0.5")

    logs = client.get(AUDIT_URL, headers=admin_headers).json()["logs"]

    assert logs[0]["ip_address"] == "10.0.0.5"


def test_csv_has_username_changes_and_imported_columns(client, db, admin_headers):
    _entry(db, user_username="jdoe", imported=True,
           changes={"first_name": {"old": "Jan", "new": "Jane"}}, ip_address="10.0.0.5")
    _entry(db, user_name=None, action="create", entity_name="Old row")

    rows = _rows(client.get(CSV_URL, headers=admin_headers))
    header = rows[0]
    by_name = {r[header.index("Entity Name")]: r for r in rows[1:]}
    new_row, old_row = by_name[""], by_name["Old row"]

    assert header[:3] == ["Timestamp", "User", "Username"]
    assert new_row[header.index("Username")] == "jdoe"
    assert new_row[header.index("Changes")] == "first_name: Jan -> Jane"
    assert new_row[header.index("Imported")] == "Yes"
    assert old_row[header.index("Username")] == ""
    assert old_row[header.index("Changes")] == ""
    assert old_row[header.index("Imported")] == "No"


def test_csv_exports_more_than_5000_rows(client, db, admin_headers):
    db.bulk_insert_mappings(AuditLog, [
        {"action": "update", "entity_type": "flight", "entity_id": i, "created_at": datetime(2026, 10, 1)}
        for i in range(5001)])
    db.commit()

    resp = client.get(CSV_URL, headers=admin_headers)

    assert resp.status_code == 200
    assert "content-length" not in resp.headers
    assert len(_rows(resp)) == 5002


def test_csv_date_filters(client, db, admin_headers):
    for day in (6, 7, 8):
        _entry(db, entity_name=f"day{day}", created_at=datetime(2026, 10, day, 15, 0))

    def names(**params):
        rows = _rows(client.get(CSV_URL, params=params, headers=admin_headers))
        # Each export is itself logged (F-17); leave the earlier exports out.
        action = rows[0].index("Action")
        return sorted(r[rows[0].index("Entity Name")] for r in rows[1:] if r[action] != "export")

    assert names(date_from="2026-10-07", date_to="2026-10-07") == ["day7"]
    assert names(date_from="2026-10-07") == ["day7", "day8"]
    assert names(date_to="2026-10-07") == ["day6", "day7"]


def test_csv_changes_are_formula_guarded(client, db, admin_headers):
    _entry(db, user_username="=cmd", changes={"=name": {"old": "=1+1", "new": "ok"}})

    rows = _rows(client.get(CSV_URL, headers=admin_headers))
    row = rows[1]

    assert row[rows[0].index("Username")] == "'=cmd"
    assert row[rows[0].index("Changes")].startswith("'")


SHAPES = {
    "pairs": {"email": {"old": EMAIL, "new": PHONE}},
    "plain": {"email": EMAIL, "phone": PHONE},
    "bulk": {"records": {"old": None, "new": "2 records: 1, 2", "ids": [1, 2], "total_ids": 2},
             "email": {"old": EMAIL, "new": None}},
    "deleted": {"deleted": {"old": f"4: first_name=Jane, email={EMAIL}, phone={PHONE}; "
                                   f"5: email={EMAIL}", "new": None}},
    "plain_trace": {"note": f"phone={PHONE}, email={EMAIL}"},
}


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_redaction_covers_every_changes_shape(shape):
    text = repr(redact_audit_changes(SHAPES[shape]))
    assert EMAIL not in text
    assert PHONE not in text


def test_redaction_hides_a_contact_value_with_punctuation():
    trace = "4: phone_work=555-0100, ext 22; call first, first_name=Jane; 5: email=a@b.org"
    redacted = redact_audit_changes({"deleted": {"old": trace, "new": None}})["deleted"]["old"]
    assert redacted == "4: phone_work=(hidden), first_name=Jane; 5: email=(hidden)"


def test_redaction_keeps_other_values():
    redacted = redact_audit_changes(SHAPES["deleted"])
    assert "first_name=Jane" in redacted["deleted"]["old"]
    assert redact_audit_changes(SHAPES["bulk"])["records"]["ids"] == [1, 2]


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_csv_redacts_contacts_without_permission(client, db, admin_headers, pilot_headers, shape):
    _entry(db, changes=SHAPES[shape])
    _hide_contacts(client, admin_headers)

    body = client.get(CSV_URL, headers=pilot_headers).text
    assert EMAIL not in body
    assert PHONE not in body
    assert EMAIL in client.get(CSV_URL, headers=admin_headers).text


def test_csv_handles_every_changes_shape_without_error(client, db, admin_headers):
    for shape in SHAPES.values():
        _entry(db, changes=shape)
    _entry(db, changes={"a": None, "b": 3, "c": ["x"]})
    _entry(db, changes=["not", "a", "dict"])

    assert len(_rows(client.get(CSV_URL, headers=admin_headers))) == 1 + len(SHAPES) + 2


def test_non_admin_cannot_change_own_display_name(client, db, pilot_user, pilot_headers):
    resp = client.patch("/api/auth/me", headers=pilot_headers, json={"display_name": "Someone Else"})
    assert resp.status_code == 403

    resp = client.patch("/api/auth/me", headers=pilot_headers,
                        json={"display_name": pilot_user.display_name, "theme": "light", "email": "p@example.org"})
    assert resp.status_code == 200, resp.text
    db.refresh(pilot_user)
    assert (pilot_user.theme, pilot_user.email) == ("light", "p@example.org")


def test_admin_can_change_any_display_name(client, db, admin_user, pilot_user, admin_headers):
    own = client.patch("/api/auth/me", headers=admin_headers, json={"display_name": "Chief"})
    other = client.patch(f"/api/auth/users/{pilot_user.id}", headers=admin_headers,
                         json={"display_name": "Renamed Pilot"})

    assert own.status_code == 200
    assert other.status_code == 200
    db.refresh(admin_user)
    db.refresh(pilot_user)
    assert (admin_user.display_name, pilot_user.display_name) == ("Chief", "Renamed Pilot")
