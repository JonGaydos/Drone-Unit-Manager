"""The interactive API docs must be off by default.

/docs, /redoc and /openapi.json hand an unauthenticated visitor the entire API
surface -- every endpoint, parameter and schema. FastAPI serves all three by
default. A black-box test of the running instance found them open, which is
free reconnaissance for anyone who reaches the app.

They are gated behind EXPOSE_API_DOCS, off unless a deployment opts in.
"""

import importlib

from fastapi.testclient import TestClient

from app.config import settings


def _client_with_docs(enabled: bool, monkeypatch):
    """A fresh app built with the flag set as asked.

    The docs URLs are decided when FastAPI() is constructed, so the module has
    to be re-imported after the flag changes rather than toggled on a live app.
    """
    monkeypatch.setattr(settings, "EXPOSE_API_DOCS", enabled)
    import app.main as main
    importlib.reload(main)
    return TestClient(main.app), main


def test_the_docs_are_off_by_default():
    assert settings.EXPOSE_API_DOCS is False


def test_docs_endpoints_are_absent_when_disabled(monkeypatch):
    client, main = _client_with_docs(False, monkeypatch)
    try:
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert client.get(path).status_code == 404, f"{path} is exposed"
    finally:
        # Leave the module as the rest of the suite expects it.
        importlib.reload(main)


def test_docs_endpoints_return_when_explicitly_enabled(monkeypatch):
    """The flag has to actually turn them back on, or it is not a real switch."""
    client, main = _client_with_docs(True, monkeypatch)
    try:
        assert client.get("/openapi.json").status_code == 200
        assert client.get("/docs").status_code == 200
        assert client.get("/redoc").status_code == 200
    finally:
        importlib.reload(main)


def test_the_health_endpoint_still_works_with_docs_off(monkeypatch):
    """Turning the docs off must not take anything else with it."""
    client, main = _client_with_docs(False, monkeypatch)
    try:
        assert client.get("/api/health").status_code == 200
    finally:
        importlib.reload(main)
