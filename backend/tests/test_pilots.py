"""Pilot merge audit-trail test.

Covers ``app.routers.pilots.merge_pilots``
(``POST /api/pilots/{target_id}/merge`` with JSON body ``{"source_id": ...}``,
supervisor-gated):

* The path pilot (``target_id``) is the merge TARGET; ``source_id`` in the body
  is the SOURCE.
* The handler writes one audit row via
  ``log_action(... "merge", "pilot", target.id ...)``.
* The human-readable merge summary ("<src> -> <tgt>") belongs in ``details``,
  NOT positionally in ``entity_name``; ``entity_name`` carries the target's
  display name (its full name).

Main-db rows are seeded via the ``db`` fixture; the app commits, so cross-session
reads see committed rows after ``expire_all``.
"""

from app.models.audit_log import AuditLog
from app.models.pilot import Pilot


def _merge_url(target_id):
    return f"/api/pilots/{target_id}/merge"


def _seed_pilot(db, *, first, last):
    p = Pilot(first_name=first, last_name=last, status="active")
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def test_merge_writes_audit_row(client, db, admin_headers):
    """The merge logs one audit row: action='merge', entity_type='pilot',
    entity_id=target.id, with the human-readable summary in details (not
    entity_name) and entity_name set to the target's full name."""
    source = _seed_pilot(db, first="Src", last="Pilot")
    target = _seed_pilot(db, first="Tgt", last="Pilot")
    source_id, target_id = source.id, target.id

    resp = client.post(
        _merge_url(target_id), json={"source_id": source_id}, headers=admin_headers
    )
    assert resp.status_code == 200, resp.text

    db.expire_all()
    rows = db.query(AuditLog).filter(
        AuditLog.action == "merge",
        AuditLog.entity_type == "pilot",
        AuditLog.entity_id == target_id,
    ).all()
    assert len(rows) == 1
    # The human-readable merge summary belongs in details, not entity_name.
    assert "Src Pilot -> Tgt Pilot" in (rows[0].details or "")
    assert "Src Pilot -> Tgt Pilot" not in (rows[0].entity_name or "")
    # entity_name carries the target's display name (its full name).
    assert rows[0].entity_name == "Tgt Pilot"
