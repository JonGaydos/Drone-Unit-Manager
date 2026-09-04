"""Operating authority CRUD and its effect on the compliance score.

An expired authority the unit depends on means every flight is unauthorised, so
it caps the 0-100 score instead of taking a proportional deduction. Records the
user has marked superseded or not-applicable stay on file for the reports but
must not score at all, and a unit with no authorities on file must be scored
exactly as it was before the feature existed.
"""

from datetime import date, timedelta

from app.models.operating_authority import AUTHORITY_SCORE_CAP, OperatingAuthority


def _seed_authority(db, **kwargs):
    defaults = {
        "authority_type": "coa",
        "title": "Blanket public safety COA",
        "identifier": "2026-WSA-1234",
        "issue_date": date.today() - timedelta(days=400),
        "record_status": "active",
        "grounds_unit": True,
    }
    defaults.update(kwargs)
    a = OperatingAuthority(**defaults)
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def _compliance(client, headers):
    resp = client.get("/api/dashboard/compliance", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


# --- CRUD ---------------------------------------------------------------


def test_create_list_update_delete(client, admin_headers):
    created = client.post("/api/operating-authorities", headers=admin_headers, json={
        "authority_type": "part_107_waiver",
        "title": "Night operations waiver",
        "identifier": "107W-2026-0001",
        "issue_date": "2026-01-01",
        "expiry_date": "2030-01-01",
        "grounds_unit": False,
        "notes": "Applies to X10 only.",
    })
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "active"
    assert body["record_status"] == "active"
    assert body["grounds_unit"] is False
    assert body["document_count"] == 0

    listed = client.get("/api/operating-authorities", headers=admin_headers)
    assert listed.status_code == 200
    assert [a["id"] for a in listed.json()] == [body["id"]]

    patched = client.patch(
        "/api/operating-authorities/{}".format(body["id"]),
        headers=admin_headers,
        json={"record_status": "superseded"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["record_status"] == "superseded"

    deleted = client.delete("/api/operating-authorities/{}".format(body["id"]), headers=admin_headers)
    assert deleted.status_code == 200
    assert client.get("/api/operating-authorities", headers=admin_headers).json() == []


def test_delete_removes_attached_documents(client, db, admin_headers, tmp_path):
    """Documents attach by (entity_type, entity_id) and SQLite reuses row ids, so
    a deleted authority must take its paperwork with it."""
    from app.models.document import Document

    a = _seed_authority(db, expiry_date=date.today() + timedelta(days=100))
    stored = tmp_path / "coa.pdf"
    stored.write_bytes(b"%PDF-1.4 test")
    db.add(Document(
        entity_type="operating_authority", entity_id=a.id, document_type="faa_authorization",
        title="COA", filename="coa.pdf", file_path=str(stored),
        mime_type="application/pdf", file_size_bytes=stored.stat().st_size,
    ))
    db.commit()

    assert client.get(f"/api/operating-authorities/{a.id}", headers=admin_headers).json()["document_count"] == 1

    assert client.delete(f"/api/operating-authorities/{a.id}", headers=admin_headers).status_code == 200

    assert db.query(Document).filter(Document.entity_type == "operating_authority").count() == 0
    assert not stored.exists()


def test_pilots_can_read_but_not_write(client, db, pilot_headers):
    _seed_authority(db, expiry_date=date.today() + timedelta(days=365))

    assert len(client.get("/api/operating-authorities", headers=pilot_headers).json()) == 1

    resp = client.post("/api/operating-authorities", headers=pilot_headers, json={
        "authority_type": "coa", "title": "Nope",
    })
    assert resp.status_code == 403


def test_invalid_type_and_record_status_rejected(client, admin_headers):
    bad_type = client.post("/api/operating-authorities", headers=admin_headers, json={
        "authority_type": "laanc", "title": "Not a supported authority",
    })
    assert bad_type.status_code == 400

    bad_status = client.post("/api/operating-authorities", headers=admin_headers, json={
        "authority_type": "coa", "title": "COA", "record_status": "retired",
    })
    assert bad_status.status_code == 400


def test_derived_status_tracks_expiry(client, db, admin_headers):
    _seed_authority(db, expiry_date=date.today() - timedelta(days=1), title="Lapsed")
    _seed_authority(db, expiry_date=date.today() + timedelta(days=30), title="Nearly due")
    _seed_authority(db, expiry_date=date.today() + timedelta(days=200), title="Fine")
    _seed_authority(db, expiry_date=None, title="No expiry")

    by_title = {a["title"]: a for a in client.get("/api/operating-authorities", headers=admin_headers).json()}

    assert by_title["Lapsed"]["status"] == "expired"
    assert by_title["Nearly due"]["status"] == "expiring"
    assert by_title["Fine"]["status"] == "active"
    assert by_title["No expiry"]["status"] == "active"
    assert by_title["No expiry"]["days_remaining"] is None


# --- Compliance score ---------------------------------------------------


def test_no_authorities_on_file_does_not_affect_score(client, admin_headers):
    """An install that has never entered an authority must score as before."""
    body = _compliance(client, admin_headers)
    assert body["operating_authorities_tracked"] == 0
    assert body["score_cap_reason"] is None
    assert body["compliance_score"] == 100


def test_expired_grounding_authority_caps_the_score(client, db, admin_headers):
    """Everything else clean, so the score would be 100 without the cap."""
    _seed_authority(db, expiry_date=date.today() - timedelta(days=5))

    body = _compliance(client, admin_headers)

    assert body["compliance_score"] == AUTHORITY_SCORE_CAP
    assert body["score_cap_reason"] == (
        "Capped at {}: 1 operating authority expired".format(AUTHORITY_SCORE_CAP)
    )
    assert len(body["expired_authorities"]) == 1
    assert body["expired_authorities"][0]["grounds_unit"] is True


def test_expired_non_grounding_authority_deducts_without_capping(client, db, admin_headers):
    """A lapsed night waiver restricts one kind of operation, not the unit."""
    _seed_authority(db, expiry_date=date.today() - timedelta(days=5), grounds_unit=False)

    body = _compliance(client, admin_headers)

    assert body["compliance_score"] == 90
    assert body["score_cap_reason"] is None


def test_expiring_authority_deducts_five(client, db, admin_headers):
    _seed_authority(db, expiry_date=date.today() + timedelta(days=45))

    body = _compliance(client, admin_headers)

    assert body["compliance_score"] == 95
    assert body["score_cap_reason"] is None
    assert len(body["expiring_authorities"]) == 1
    assert body["expiring_authorities"][0]["days_remaining"] == 45


def test_superseded_and_not_applicable_records_are_not_scored(client, db, admin_headers):
    """History the unit has retired must not pin the score at the cap forever."""
    _seed_authority(db, expiry_date=date.today() - timedelta(days=400), record_status="superseded")
    _seed_authority(db, expiry_date=date.today() - timedelta(days=200), record_status="not_applicable")
    _seed_authority(db, expiry_date=date.today() + timedelta(days=300))

    body = _compliance(client, admin_headers)

    assert body["compliance_score"] == 100
    assert body["score_cap_reason"] is None
    assert body["expired_authorities"] == []
    assert body["operating_authorities_tracked"] == 1  # active records only


def test_cap_wins_over_other_deductions(client, db, admin_headers):
    """The cap is a ceiling, not a deduction: other problems still lower the
    score beneath it, but nothing raises it above."""
    _seed_authority(db, expiry_date=date.today() - timedelta(days=5))
    _seed_authority(db, expiry_date=date.today() + timedelta(days=10), title="Also nearly due")

    body = _compliance(client, admin_headers)

    assert body["compliance_score"] == AUTHORITY_SCORE_CAP


def test_multiple_expired_authorities_pluralize_the_reason(client, db, admin_headers):
    _seed_authority(db, expiry_date=date.today() - timedelta(days=5), title="COA")
    _seed_authority(db, expiry_date=date.today() - timedelta(days=6), title="BVLOS waiver",
                    authority_type="part_107_waiver")

    body = _compliance(client, admin_headers)

    assert body["score_cap_reason"] == (
        "Capped at {}: 2 operating authorities expired".format(AUTHORITY_SCORE_CAP)
    )


# --- Reports ------------------------------------------------------------


def test_certifications_report_appends_authorities_section(client, db, admin_headers):
    _seed_authority(db, expiry_date=date.today() + timedelta(days=100))

    resp = client.post("/api/reports/generate", headers=admin_headers,
                       json={"report_type": "pilot_certifications"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    titles = [s["title"] for s in body["sections"]]
    assert titles == ["Pilot Certifications", "Operating Authorities"]
    assert body["sections"][1]["rows"][0]["identifier"] == "2026-WSA-1234"


def test_annual_report_lists_authorities_held_during_the_period(client, db, admin_headers):
    """Authorities that lapsed before the period started are left out."""
    _seed_authority(db, title="Held during 2026",
                    issue_date=date(2026, 1, 1), expiry_date=date(2026, 12, 31))
    _seed_authority(db, title="Lapsed in 2024",
                    issue_date=date(2023, 1, 1), expiry_date=date(2024, 6, 1))

    resp = client.post("/api/reports/generate", headers=admin_headers,
                       json={"report_type": "annual_unit_report",
                             "date_from": "2026-01-01", "date_to": "2026-12-31"})

    assert resp.status_code == 200, resp.text
    section = next(s for s in resp.json()["sections"] if s["title"] == "Operating Authorities")
    assert [r["title"] for r in section["rows"]] == ["Held during 2026"]
