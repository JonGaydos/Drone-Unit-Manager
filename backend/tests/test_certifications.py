"""Certification bulk-renew tests: month-end date math + batch resilience + authz.

Covers the real behavior of ``app.routers.certifications`` bulk-renew, whose
expiry is auto-calculated from the cert type's ``renewal_period_months`` via
``_do_renew`` (lines computing ``m = issue.month + months`` then a
``calendar.monthrange`` clamp ``day=min(issue.day, last_day)``):

* POST ``/api/pilot-certifications/bulk-renew`` (supervisor/admin) renews each
  selected non-renewed cert with one issue date, expiry auto-calculated per type.
* Month-end math: Jan 31 + 1 month clamps to the last day of February (Feb 28 in
  a common year, Feb 29 in a leap year) with NO ValueError/500 -- the
  ``min(day, last_day)`` clamp prevents the naive "Feb 31" crash.
* Year rollover: a 12-month renewal from Feb 29 (leap) clamps to Feb 28 the
  following (common) year.
* Batch resilience: a batch mixing valid ids, a nonexistent id, and an
  already-renewed cert renews only the valid non-renewed ones; the bad/skipped
  items do not abort the batch.
* Bulk-renew is supervisor-gated; a pilot gets 403.

Main-db rows are seeded via the ``db`` fixture; the app commits, so cross-session
reads see committed rows after ``expire_all``.
"""

from datetime import date

from app.models.certification import CertificationType, PilotCertification
from app.models.pilot import Pilot

BULK_RENEW_URL = "/api/pilot-certifications/bulk-renew"


def _seed_pilot(db):
    pilot = Pilot(first_name="Test", last_name="Pilot", status="active")
    db.add(pilot)
    db.commit()
    db.refresh(pilot)
    return pilot


def _seed_cert_type(db, *, name="Type", months=1):
    ct = CertificationType(name=name, category="custom", has_expiration=True,
                           renewal_period_months=months)
    db.add(ct)
    db.commit()
    db.refresh(ct)
    return ct


def _seed_cert(db, *, pilot_id, cert_type_id, issue_date, expiration_date=None,
               status="complete"):
    pc = PilotCertification(
        pilot_id=pilot_id,
        certification_type_id=cert_type_id,
        status=status,
        issue_date=issue_date,
        expiration_date=expiration_date,
    )
    db.add(pc)
    db.commit()
    db.refresh(pc)
    return pc


def _latest_renewal(db, old_id):
    """The new cert created by renewing ``old_id`` (linked via renewed_from_id)."""
    db.expire_all()
    return db.query(PilotCertification).filter(
        PilotCertification.renewed_from_id == old_id
    ).one()


def test_bulk_renew_jan31_one_month_clamps_to_end_of_february(client, db, admin_headers):
    """Jan 31 + 1 month -> Feb 28 (common year), no ValueError/500."""
    pilot = _seed_pilot(db)
    ct = _seed_cert_type(db, months=1)
    old = _seed_cert(db, pilot_id=pilot.id, cert_type_id=ct.id,
                     issue_date=date(2025, 1, 31))

    resp = client.post(BULK_RENEW_URL, headers=admin_headers, json={
        "pilot_certification_ids": [old.id],
        "issue_date": "2025-01-31",
    })

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True, "renewed": 1}

    new = _latest_renewal(db, old.id)
    assert new.issue_date == date(2025, 1, 31)
    assert new.expiration_date == date(2025, 2, 28)
    assert new.status == "complete"
    db.refresh(old)
    assert old.status == "renewed"


def test_bulk_renew_jan31_one_month_leap_year_clamps_to_feb29(client, db, admin_headers):
    """Jan 31 + 1 month in a leap year -> Feb 29, no crash."""
    pilot = _seed_pilot(db)
    ct = _seed_cert_type(db, months=1)
    old = _seed_cert(db, pilot_id=pilot.id, cert_type_id=ct.id,
                     issue_date=date(2024, 1, 31))

    resp = client.post(BULK_RENEW_URL, headers=admin_headers, json={
        "pilot_certification_ids": [old.id],
        "issue_date": "2024-01-31",
    })

    assert resp.status_code == 200, resp.text
    new = _latest_renewal(db, old.id)
    assert new.expiration_date == date(2024, 2, 29)


def test_bulk_renew_feb29_twelve_months_clamps_to_feb28_next_year(client, db, admin_headers):
    """12-month renewal from leap Feb 29 -> Feb 28 the next (common) year."""
    pilot = _seed_pilot(db)
    ct = _seed_cert_type(db, months=12)
    old = _seed_cert(db, pilot_id=pilot.id, cert_type_id=ct.id,
                     issue_date=date(2024, 2, 29))

    resp = client.post(BULK_RENEW_URL, headers=admin_headers, json={
        "pilot_certification_ids": [old.id],
        "issue_date": "2024-02-29",
    })

    assert resp.status_code == 200, resp.text
    new = _latest_renewal(db, old.id)
    assert new.expiration_date == date(2025, 2, 28)


def test_bulk_renew_batch_resilient_to_bad_and_renewed_items(client, db, admin_headers):
    """A batch mixing valid ids, a nonexistent id, and an already-renewed cert
    renews only the valid non-renewed ones; bad/skipped items do not abort."""
    pilot = _seed_pilot(db)
    ct = _seed_cert_type(db, months=1)

    good1 = _seed_cert(db, pilot_id=pilot.id, cert_type_id=ct.id,
                       issue_date=date(2025, 1, 31))
    good2 = _seed_cert(db, pilot_id=pilot.id, cert_type_id=ct.id,
                       issue_date=date(2025, 3, 15))
    already = _seed_cert(db, pilot_id=pilot.id, cert_type_id=ct.id,
                         issue_date=date(2025, 1, 1), status="renewed")
    nonexistent_id = 999999

    resp = client.post(BULK_RENEW_URL, headers=admin_headers, json={
        "pilot_certification_ids": [good1.id, nonexistent_id, already.id, good2.id],
        "issue_date": "2025-06-14",
    })

    assert resp.status_code == 200, resp.text
    # Only the two valid, non-renewed certs are renewed.
    assert resp.json() == {"ok": True, "renewed": 2}

    new1 = _latest_renewal(db, good1.id)
    new2 = _latest_renewal(db, good2.id)
    assert new1.expiration_date == date(2025, 7, 14)
    assert new2.expiration_date == date(2025, 7, 14)

    db.refresh(good1)
    db.refresh(good2)
    db.refresh(already)
    assert good1.status == "renewed"
    assert good2.status == "renewed"
    # The pre-renewed cert spawned no new cert.
    assert db.query(PilotCertification).filter(
        PilotCertification.renewed_from_id == already.id
    ).count() == 0


def test_bulk_renew_requires_supervisor_role(client, db, pilot_headers):
    """A pilot-role user is rejected with 403; no cert is renewed."""
    pilot = _seed_pilot(db)
    ct = _seed_cert_type(db, months=1)
    old = _seed_cert(db, pilot_id=pilot.id, cert_type_id=ct.id,
                     issue_date=date(2025, 1, 31))

    resp = client.post(BULK_RENEW_URL, headers=pilot_headers, json={
        "pilot_certification_ids": [old.id],
        "issue_date": "2025-01-31",
    })

    assert resp.status_code == 403, resp.text
    db.refresh(old)
    assert old.status == "complete"
    assert db.query(PilotCertification).filter(
        PilotCertification.renewed_from_id == old.id
    ).count() == 0
