"""Vehicle merge audit-trail test.

Covers ``app.routers.vehicles.merge_vehicles``
(``POST /api/vehicles/{target_id}/merge?merge_from_id=<source>``,
supervisor-gated):

* The path vehicle (``target_id``) is the merge TARGET; ``merge_from_id`` is the
  SOURCE.
* The handler writes one audit row via
  ``log_action(... "merge", "vehicle", target.id ...)``.
* The human-readable merge summary ("<src> -> <tgt>") belongs in ``details``,
  NOT positionally in ``entity_name``; ``entity_name`` carries the target's
  display name (manufacturer/model plus optional nickname).

Main-db rows are seeded via the ``db`` fixture; the app commits, so cross-session
reads see committed rows after ``expire_all``.
"""

from app.models.audit_log import AuditLog
from app.models.vehicle import Vehicle


def _merge_url(target_id, source_id):
    return f"/api/vehicles/{target_id}/merge?merge_from_id={source_id}"


def _seed_vehicle(db, *, serial, manufacturer, model, nickname=None):
    v = Vehicle(
        serial_number=serial,
        manufacturer=manufacturer,
        model=model,
        nickname=nickname,
        status="active",
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def test_merge_writes_audit_row(client, db, admin_headers):
    """The merge logs one audit row: action='merge', entity_type='vehicle',
    entity_id=target.id, with the human-readable summary in details (not
    entity_name) and entity_name set to the target's display name."""
    source = _seed_vehicle(db, serial="SRC-V1", manufacturer="Skydio", model="X10")
    target = _seed_vehicle(db, serial="TGT-V1", manufacturer="Skydio", model="X2E")
    source_id, target_id = source.id, target.id

    resp = client.post(_merge_url(target_id, source_id), headers=admin_headers)
    assert resp.status_code == 200, resp.text

    db.expire_all()
    rows = db.query(AuditLog).filter(
        AuditLog.action == "merge",
        AuditLog.entity_type == "vehicle",
        AuditLog.entity_id == target_id,
    ).all()
    assert len(rows) == 1
    # The human-readable merge summary belongs in details, not entity_name.
    assert "Skydio X10 -> Skydio X2E" in (rows[0].details or "")
    assert "Skydio X10 -> Skydio X2E" not in (rows[0].entity_name or "")
    # entity_name carries the target's display name (manufacturer/model).
    assert rows[0].entity_name == "Skydio X2E"
