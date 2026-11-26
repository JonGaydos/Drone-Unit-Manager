"""The health endpoints.

/api/health is public, for the container HEALTHCHECK and uptime monitors, so it
says up or down and nothing else. Which services the app uses, whether backups
and syncs are stale, and the version are for admins at /api/health/details.

The version is how an operator tells one container from another: production
tracks a released tag and staging tracks ``:main``, and for most of a release
cycle those are different builds of the same app. It has to come from one place
and actually change when that place does.
"""

from app.constants import APP_TITLE, APP_VERSION


def test_public_health_says_up_and_nothing_else(client):
    """An unauthenticated visitor learned the services the app uses and whether
    backups and syncs were stale (external review, 2026-11)."""
    resp = client.get("/api/health")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_public_health_is_503_and_bare_when_a_database_is_down(client, monkeypatch):
    from app import database

    class Unreachable:
        def execute(self, *_):
            raise RuntimeError("database file is locked")

        def close(self):
            pass

    monkeypatch.setattr(database, "TelemetrySessionLocal", Unreachable)
    resp = client.get("/api/health")

    assert resp.status_code == 503
    assert resp.json() == {"status": "unhealthy"}


def test_health_details_need_an_admin(client, pilot_headers):
    assert client.get("/api/health/details").status_code == 401
    assert client.get("/api/health/details", headers=pilot_headers).status_code == 403


def test_health_details_report_the_version_the_build_was_cut_from(client, admin_headers):
    body = client.get("/api/health/details", headers=admin_headers).json()

    assert body["status"] == "ok"
    assert body["app"] == APP_TITLE
    assert body["version"] == APP_VERSION
    assert body["database"] == "connected"


def test_the_openapi_document_reports_the_same_version():
    """Two copies of the literal used to drift apart unnoticed; the version the
    app reports and the version in its schema have to agree.

    The schema lives at app.openapi_version regardless of whether /openapi.json
    is served -- the docs are gated off by default, so this reads the app object
    rather than the (404) route."""
    from app.main import app
    assert app.openapi()["info"]["version"] == APP_VERSION


def test_the_version_is_not_a_placeholder():
    assert APP_VERSION
    assert APP_VERSION[0].isdigit(), APP_VERSION
