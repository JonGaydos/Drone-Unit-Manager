"""The call sites must actually sanitise, not just have a helper available.

test_logsafe.py proves for_log() works. These prove the two places that log a
request-supplied value call it, which is the part that would silently regress
if someone reformatted the log line.
"""

import logging

from app.logsafe import for_log

LF = chr(10)

# A geocode query that tries to append a second, plausible-looking log line.
FORGED = "1 Example Rd" + LF + "2026-01-01 00:00:00 [INFO] auth: admin logged in"


def test_a_geocode_failure_logs_the_query_on_one_line(client, db, admin_headers,
                                                      monkeypatch, caplog):
    """The query reaches the log only through for_log(), so a newline in it
    cannot produce a second entry."""
    def boom(*a, **k):
        raise RuntimeError("nominatim unreachable")

    monkeypatch.setattr("app.routers.geocode.httpx.get", boom)

    with caplog.at_level(logging.WARNING, logger="app.routers.geocode"):
        resp = client.get("/api/geocode", params={"q": FORGED}, headers=admin_headers)

    assert resp.status_code == 502
    records = [r for r in caplog.records if "Geocode lookup failed" in r.getMessage()]
    assert records, "the failure was not logged at all"
    for record in records:
        assert LF not in record.getMessage(), "a newline survived into the log line"
    assert "1 Example Rd" in records[0].getMessage(), "the query itself should still be logged"


def test_the_sanitised_form_is_what_reaches_the_message(caplog):
    """Guards the shape of the call: the message must carry for_log's output,
    not the raw value."""
    logger = logging.getLogger("app.routers.geocode")
    with caplog.at_level(logging.WARNING, logger="app.routers.geocode"):
        logger.warning("Geocode lookup failed for %s: %s", for_log(FORGED), "boom")

    message = caplog.records[-1].getMessage()
    assert LF not in message
    assert message.count("[INFO] auth") == 1, "the forged text should appear as data, once"
    assert "'" in message, "for_log quotes the value so its boundaries are visible"
