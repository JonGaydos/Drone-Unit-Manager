"""Unset purpose and the real "Unknown" purpose must not collide.

"Unknown" is a selectable flight purpose. The analytics also turned a NULL
purpose into the label "Unknown", so a flight with no purpose and a flight
deliberately marked "Unknown" landed in two group rows that displayed
identically -- and editing a flight between the two states looked like it
changed nothing on the chart.

Found on a real instance: flights-by-purpose returned two "Unknown" rows, 171
(NULL) and 68 (the literal). Unset flights are now "Unspecified", distinct from
the purpose.
"""

from datetime import date

from app.models.flight import Flight

BY_PURPOSE = "/api/dashboard/analytics/flights-by-purpose"
BY_YEAR_PURPOSE = "/api/dashboard/analytics/flights-by-year-purpose"


def _seed(db, **kw):
    kw.setdefault("date", date(2025, 6, 1))
    kw.setdefault("counts_toward_totals", True)
    f = Flight(**kw)
    db.add(f)
    db.commit()
    return f


def test_null_and_literal_unknown_are_separate_buckets(client, db, admin_headers):
    _seed(db, purpose=None)
    _seed(db, purpose=None)
    _seed(db, purpose="Unknown")

    rows = {r["purpose"]: r["count"] for r in client.get(BY_PURPOSE, headers=admin_headers).json()}

    assert rows.get("Unspecified") == 2, "NULL-purpose flights should be Unspecified"
    assert rows.get("Unknown") == 1, "a flight marked Unknown stays Unknown"
    assert list(rows).count("Unspecified") <= 1
    # the collision: never two rows that read the same
    labels = [r["purpose"] for r in client.get(BY_PURPOSE, headers=admin_headers).json()]
    assert len(labels) == len(set(labels)), f"duplicate label in {labels}"


def test_an_empty_string_purpose_also_folds_to_unspecified(client, db, admin_headers):
    """Some imports write "" rather than NULL; it means the same thing."""
    _seed(db, purpose="")
    _seed(db, purpose=None)

    rows = {r["purpose"]: r["count"] for r in client.get(BY_PURPOSE, headers=admin_headers).json()}

    assert rows.get("Unspecified") == 2
    assert "" not in rows


def test_editing_a_flight_from_unset_to_a_purpose_moves_it(client, db, admin_headers):
    """The symptom that started this: the edit has to visibly move the flight
    off Unspecified and onto the chosen purpose."""
    f = _seed(db, purpose=None)

    before = {r["purpose"]: r["count"] for r in client.get(BY_PURPOSE, headers=admin_headers).json()}
    assert before.get("Unspecified") == 1

    f.purpose = "Training"
    db.commit()

    after = {r["purpose"]: r["count"] for r in client.get(BY_PURPOSE, headers=admin_headers).json()}
    assert "Unspecified" not in after
    assert after.get("Training") == 1


def test_the_year_purpose_breakdown_uses_the_same_label(client, db, admin_headers):
    _seed(db, purpose=None, date=date(2025, 3, 1))
    _seed(db, purpose="Unknown", date=date(2025, 3, 1))

    rows = client.get(BY_YEAR_PURPOSE, headers=admin_headers).json()
    labels = {r["purpose"] for r in rows}

    assert "Unspecified" in labels
    assert "Unknown" in labels
