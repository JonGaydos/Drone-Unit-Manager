"""The health endpoint is how an operator tells one container from another.

Production tracks a released tag and staging tracks ``:main``, and for most of
a release cycle those are different builds of the same app. The version string
is the only thing in the response that distinguishes them, so it has to come
from one place and actually change when that place does.
"""

from app.constants import APP_TITLE, APP_VERSION


def test_health_reports_the_version_the_build_was_cut_from(client):
    body = client.get("/api/health").json()

    assert body["status"] == "ok"
    assert body["app"] == APP_TITLE
    assert body["version"] == APP_VERSION
    assert body["database"] == "connected"


def test_the_openapi_document_reports_the_same_version(client):
    """Two copies of the literal used to drift apart unnoticed; the API docs
    and the health endpoint have to agree."""
    assert client.get("/openapi.json").json()["info"]["version"] == APP_VERSION


def test_the_version_is_not_a_placeholder():
    assert APP_VERSION
    assert APP_VERSION[0].isdigit(), APP_VERSION
