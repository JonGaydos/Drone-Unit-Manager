"""Per-pilot Needs Attention: certifications (moved from the currency tests).

GET ``/api/pilots/{id}/needs-attention`` lists certifications whose
``expiration_date`` is set: already past -> level "red"; expiring within 30
days -> level "amber"; further out or no expiration -> omitted. Response shape:
``{"count": int, "items": [{"level", "category", "text"}]}``.
"""

from datetime import date, timedelta

from app.models.certification import CertificationType, PilotCertification
from app.models.pilot import Pilot

TODAY = date.today()


def _seed_pilot(db, *, last):
    pilot = Pilot(first_name="Test", last_name=last, status="active")
    db.add(pilot)
    db.commit()
    db.refresh(pilot)
    return pilot


def _seed_cert_type(db, *, name):
    ct = CertificationType(name=name, category="custom", has_expiration=True)
    db.add(ct)
    db.commit()
    db.refresh(ct)
    return ct


def _seed_cert(db, *, pilot_id, cert_type_id, expiration_date):
    db.add(PilotCertification(pilot_id=pilot_id, certification_type_id=cert_type_id,
                              status="complete", expiration_date=expiration_date))
    db.commit()


def test_needs_attention_red_and_amber_certs(client, db, admin_headers):
    """An expired cert (red), an expiring-soon cert (amber) and a far-future
    cert (omitted)."""
    pilot = _seed_pilot(db, last="Mixed")
    expired_date = TODAY - timedelta(days=5)
    soon_date = TODAY + timedelta(days=10)
    for name, expires in (("Expired Cert", expired_date), ("Soon Cert", soon_date),
                          ("Valid Cert", TODAY + timedelta(days=365))):
        _seed_cert(db, pilot_id=pilot.id, cert_type_id=_seed_cert_type(db, name=name).id,
                   expiration_date=expires)

    resp = client.get(f"/api/pilots/{pilot.id}/needs-attention", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["count"] == 2

    reds = [i for i in payload["items"] if i["level"] == "red"]
    ambers = [i for i in payload["items"] if i["level"] == "amber"]
    assert [i["category"] for i in reds] == ["certification"]
    assert [i["category"] for i in ambers] == ["certification"]
    assert "Expired Cert" in reds[0]["text"]
    assert str(expired_date) in reds[0]["text"]
    assert "Soon Cert" in ambers[0]["text"]
    assert str(soon_date) in ambers[0]["text"]
    assert all("Valid Cert" not in i["text"] for i in payload["items"])


def test_needs_attention_null_expiration_omitted(client, db, admin_headers):
    pilot = _seed_pilot(db, last="NoExpiry")
    ct = _seed_cert_type(db, name="No Expiry Cert")
    _seed_cert(db, pilot_id=pilot.id, cert_type_id=ct.id, expiration_date=None)

    resp = client.get(f"/api/pilots/{pilot.id}/needs-attention", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"count": 0, "items": []}


def test_needs_attention_unknown_pilot_404(client, db, admin_headers):
    resp = client.get("/api/pilots/999999/needs-attention", headers=admin_headers)
    assert resp.status_code == 404, resp.text


def test_needs_attention_requires_auth(client, db):
    resp = client.get("/api/pilots/1/needs-attention")
    assert resp.status_code == 401, resp.text
