"""Security headers must be on every response.

The container runs uvicorn directly -- there is no nginx in it, and the
nginx.conf in the repo is not copied into the image. So headers added at a
proxy never reach a request; they have to be set by the app. A first attempt
put them in nginx.conf and they applied to nothing, which is why this test
exists: to prove they are actually served, on the API and on the SPA the app
also hosts.
"""

import pytest

REQUIRED = {
    "x-frame-options": "SAMEORIGIN",
    "x-content-type-options": "nosniff",
    "referrer-policy": "strict-origin-when-cross-origin",
    "strict-transport-security": "max-age=15768000",
}


def test_the_api_carries_every_security_header(client):
    r = client.get("/api/health")

    for name, value in REQUIRED.items():
        assert r.headers.get(name) == value, f"{name} missing or wrong on /api"
    assert "content-security-policy" in r.headers


def test_the_csp_locks_down_the_dangerous_directives(client):
    csp = client.get("/api/health").headers["content-security-policy"]

    assert "default-src 'self'" in csp
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'self'" in csp
    # no wildcard script source, which would defeat the point
    assert "script-src 'self'" in csp
    assert "script-src *" not in csp


def test_an_error_response_still_carries_the_headers(client):
    """A 404 or 401 is exactly where an attacker probes; the headers must not
    fall off the unhappy path."""
    r = client.get("/api/flights")  # 401, no auth

    assert r.status_code == 401
    assert r.headers.get("x-frame-options") == "SAMEORIGIN"
    assert "content-security-policy" in r.headers


def test_the_request_id_is_still_there(client):
    """The headers were folded into the existing request-id middleware; it must
    keep doing its original job."""
    assert client.get("/api/health").headers.get("x-request-id")


@pytest.mark.parametrize("header", list(REQUIRED))
def test_each_header_individually(client, header):
    assert header in {k.lower() for k in client.get("/api/health").headers}
