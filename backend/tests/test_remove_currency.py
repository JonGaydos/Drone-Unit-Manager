"""Currency is gone: no routes, no dashboard fields, no Needs Attention items,
no score part and no token area. Flight Requirements replace it."""

from datetime import date, timedelta

import pytest

from app.models.currency_rule import CurrencyRule
from app.models.flight import Flight
from app.models.pilot import Pilot
from app.services import api_tokens, permissions

COMPLIANCE_URL = "/api/dashboard/compliance"


@pytest.fixture
def lapsed_pilot(db):
    """An active pilot who would be lapsed on an active currency rule: the
    rule row can still exist until migration 0018 drops the table."""
    db.add(CurrencyRule(name="Monthly hour", required_hours=5, period_days=30, is_active=True))
    pilot = Pilot(first_name="Lee", last_name="Lapsed", status="active")
    db.add(pilot)
    db.commit()
    db.add(Flight(pilot_id=pilot.id, date=date.today() - timedelta(days=60),
                  duration_seconds=600, review_status="reviewed"))
    db.commit()
    db.refresh(pilot)
    return pilot


@pytest.mark.parametrize("method,url", [
    ("get", "/api/currency/rules"),
    ("post", "/api/currency/rules"),
    ("get", "/api/currency/status"),
    ("get", "/api/currency/status/1"),
    ("get", "/api/currency/models"),
    ("post", "/api/currency/send-reminders"),
    ("post", "/api/currency/send-reminders/start"),
    ("get", "/api/currency/jobs/abc"),
])
def test_currency_routes_are_gone(client, admin_headers, method, url):
    # A POST to an unknown path meets the SPA's GET catch-all and gets 405.
    resp = client.request(method.upper(), url, headers=admin_headers, json={})
    assert resp.status_code in (404, 405)


def test_no_currency_route_is_registered():
    from app.main import app
    assert [r.path for r in app.routes if getattr(r, "path", "").startswith("/api/currency")] == []


def test_needs_attention_has_no_currency_items(client, admin_headers, lapsed_pilot):
    body = client.get(f"/api/pilots/{lapsed_pilot.id}/needs-attention", headers=admin_headers).json()
    assert [item for item in body["items"] if item["category"] == "currency"] == []


@pytest.mark.parametrize("field", [
    "pilot_currency_status", "currency_rules_active", "pilots_lapsed", "pilots_current",
])
def test_compliance_payload_has_no_currency_fields(client, admin_headers, lapsed_pilot, field):
    assert field not in client.get(COMPLIANCE_URL, headers=admin_headers).json()


def test_compliance_score_has_no_currency_part(client, admin_headers, lapsed_pilot):
    assert client.get(COMPLIANCE_URL, headers=admin_headers).json()["compliance_score"] == 100


def test_certifications_feature_label():
    assert permissions.REGISTRY["certifications.view"].feature == "Certifications"


def test_certifications_manage_label_drops_reminders():
    assert permissions.REGISTRY["certifications.manage"].action == "Manage"


def test_pilots_token_area_has_no_currency_prefix():
    assert "/api/currency" not in api_tokens.SCOPE_PREFIXES["pilots"]
