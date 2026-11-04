"""Automatic audit capture: every ORM create, update and delete gets an entry.

A session hook writes the entries in the same transaction as the change, so
the change and its record commit together or not at all. ``log_action`` entries
take the place of the automatic entry for the same record. Inside
``machine_run`` the hook counts changes instead and keeps one summary row.

The hook runs in two steps. ``before_flush`` reads old values while they are
still available, and ``after_flush_postexec`` writes entries once new rows have
IDs. It is the post-flush event that allows changing rows already flushed, and
``Session.commit`` flushes again until nothing is left, so the entries are in
the commit.

This module is imported by ``app.database``, so it imports models and
``app.services.audit`` inside the functions that use them.
"""

import re
from contextlib import contextmanager
from dataclasses import dataclass, field

from sqlalchemy import event, inspect, select

from app.constants import SECRET_KEYS

ACTOR_KEY = "audit_actor"
_STATE_KEY = "audit_capture"

SYSTEM_USER_NAME = "System"
CREATE = "create"
UPDATE = "update"
DELETE = "delete"
_ACTIONS = (CREATE, UPDATE, DELETE)

_AUDIT_LOG_MODEL = "AuditLog"
_SETTING_MODEL = "Setting"
_SETTING_VALUE_FIELD = "value"

EXCLUDED_MODELS = frozenset({_AUDIT_LOG_MODEL, "NotificationLog", "Alert"})
# Bookkeeping, plus the display theme, a personal preference.
EXCLUDED_FIELDS = frozenset({
    "created_at", "updated_at", "last_used_at", "token_version", "modified_by_id", "theme",
})
SECRET_FIELDS = frozenset({"password_hash", "token_hash"})
SECRET_MARKER = "[changed]"
# Settings the app itself writes to report on its own jobs.
SYSTEM_STATUS_SETTING_KEYS = frozenset({
    "last_sync_at", "last_sync_timestamp", "last_sync_provider", "last_sync_result",
    "last_telemetry_sync_timestamp", "last_telemetry_sync_result",
    "last_backup_at", "last_backup_result",
})
MACHINE_RUN_ID_CAP = 500

# entity_type where it differs from the snake_case class name. These are the
# names log_action calls already use.
_ENTITY_TYPE_OVERRIDES = {
    "MaintenanceRecord": "maintenance",
    "EquipmentCheckout": "equipment",
    "SensorPackage": "sensor",
}
_ENTITY_NAME_ATTRS = (
    "full_name", "name", "title", "username", "key", "entity_name", "nickname",
    "serial_number", "original_filename", "filename",
)
_ENTITY_NAME_MAX = 300
_CAMEL_BOUNDARY = re.compile(r"(?<!^)(?=[A-Z])")


@dataclass
class _Captured:
    """One object seen by ``before_flush``, waiting for the flush to finish."""
    obj: object
    action: str
    entity_name: str | None
    changes: dict | None


@dataclass
class _MachineRun:
    """Counts for one machine run, and the one row that reports them.

    ``frames[0]`` holds what is committed, ``frames[1]`` the open transaction,
    and any further frames open savepoints, so a rollback can drop just its own
    part. Each frame maps ``(model name, action)`` to record IDs.
    """
    action: str
    entity_type: str
    details: str | None
    frames: list = field(default_factory=lambda: [{}, {}])
    entry: object = None
    stale: bool = False

    def tally(self, model: str, action: str, record_id) -> None:
        self.frames[-1].setdefault((model, action), set()).add(record_id)
        self.stale = True

    def merge_top_frame(self) -> None:
        top = self.frames.pop()
        for tally_key, ids in top.items():
            self.frames[-1].setdefault(tally_key, set()).update(ids)

    def summary(self) -> dict:
        """Per model: counts, IDs capped with the total stated, and the same
        as text in the ``new`` slot, which is what the log page displays."""
        by_model: dict = {}
        for frame in self.frames:
            for (model, action), ids in frame.items():
                by_model.setdefault(model, {}).setdefault(action, set()).update(ids)
        return {model: _model_summary(actions) for model, actions in by_model.items()}


@dataclass
class _CaptureState:
    pending: list = field(default_factory=list)
    automatic: dict = field(default_factory=dict)
    explicit: dict = field(default_factory=dict)
    run: _MachineRun | None = None


def _model_summary(actions: dict) -> dict:
    counts = {action: len(actions.get(action, ())) for action in _ACTIONS}
    all_ids = sorted(set().union(*actions.values()))
    ids = all_ids[:MACHINE_RUN_ID_CAP]
    text = (
        f"{counts[CREATE]} created, {counts[UPDATE]} updated, {counts[DELETE]} deleted; "
        f"{len(all_ids)} records: {', '.join(str(i) for i in ids)}"
    )
    if len(all_ids) > len(ids):
        text += f" (first {len(ids)} shown)"
    return {"old": None, "new": text, "counts": counts, "ids": ids, "total_ids": len(all_ids)}


def _state(session) -> _CaptureState:
    return session.info.setdefault(_STATE_KEY, _CaptureState())


def set_actor(session, user) -> None:
    """Record who is acting on this session, for every entry written through it."""
    session.info[ACTOR_KEY] = {"id": user.id, "name": user.display_name, "username": user.username}


def entity_type_of(model_class) -> str:
    """The audit ``entity_type`` for a model class."""
    name = model_class.__name__
    return _ENTITY_TYPE_OVERRIDES.get(name) or _CAMEL_BOUNDARY.sub("_", name).lower()


def _is_status_setting(obj) -> bool:
    return type(obj).__name__ == _SETTING_MODEL and obj.key in SYSTEM_STATUS_SETTING_KEYS


def _is_captured(obj, run) -> bool:
    """Whether a change to ``obj`` is recorded. A machine run counts the models
    left out of per-row capture, since writing those is often the run's job."""
    name = type(obj).__name__
    if name == _AUDIT_LOG_MODEL or _is_status_setting(obj):
        return False
    return run is not None or name not in EXCLUDED_MODELS


def _is_secret(obj, attr_key: str) -> bool:
    if attr_key in SECRET_FIELDS:
        return True
    return (
        type(obj).__name__ == _SETTING_MODEL
        and attr_key == _SETTING_VALUE_FIELD
        and obj.key in SECRET_KEYS
    )


def _format(obj, attr_key: str, old, new) -> dict:
    from app.services.audit import _fmt_change

    if _is_secret(obj, attr_key):
        return {"old": SECRET_MARKER, "new": SECRET_MARKER}
    return _fmt_change(old, new)


def _recorded_keys(mapper):
    """Column attributes an entry may mention: not the key, not bookkeeping."""
    primary = {column.key for column in mapper.primary_key}
    return [
        attr.key for attr in mapper.column_attrs
        if attr.key not in EXCLUDED_FIELDS and attr.columns[0].key not in primary
    ]


def _stored_values(session, obj_state, keys: list[str]) -> dict:
    """Read current database values. An attribute set while expired (after a
    commit) has no old value in memory."""
    mapper = obj_state.mapper
    columns = [mapper.get_property(key).columns[0] for key in keys]
    conditions = [pk == value for pk, value in zip(mapper.primary_key, obj_state.identity)]
    row = session.execute(select(*columns).where(*conditions)).one_or_none()
    return dict(zip(keys, row)) if row is not None else {}


def _changed_values(session, obj_state) -> dict:
    """``{key: (old, new)}`` for each recorded attribute with pending changes."""
    pairs: dict = {}
    old_unknown = []
    for key in _recorded_keys(obj_state.mapper):
        history = obj_state.attrs[key].history
        if history.has_changes():
            new = history.added[0] if history.added else None
            pairs[key] = (history.deleted[0] if history.deleted else None, new)
            if not history.deleted:
                old_unknown.append(key)
    if old_unknown:
        stored = _stored_values(session, obj_state, old_unknown)
        pairs.update({key: (stored.get(key), pairs[key][1]) for key in old_unknown})
    return pairs


def _update_changes(session, obj) -> dict:
    pairs = _changed_values(session, inspect(obj))
    return {
        key: _format(obj, key, old, new)
        for key, (old, new) in pairs.items()
        if str(old) != str(new)
    }


def _create_changes(obj) -> dict:
    """Values of a new row. Reads the instance dict because a column the
    database filled in has expired and needs no reload for this."""
    values = inspect(obj).dict
    return {
        key: _format(obj, key, None, values[key])
        for key in _recorded_keys(inspect(obj).mapper)
        if values.get(key) is not None
    }


def _delete_changes(obj) -> dict:
    """The record's non-empty fields, kept as its identifying trace."""
    mapper = inspect(obj).mapper
    old_values = {key: getattr(obj, key) for key in _recorded_keys(mapper)}
    return {key: _format(obj, key, value, None) for key, value in old_values.items() if value is not None}


def _entity_name(obj) -> str | None:
    for attr in _ENTITY_NAME_ATTRS:
        value = getattr(obj, attr, None)
        if value:
            return str(value)[:_ENTITY_NAME_MAX]
    return None


def _record_key(obj) -> tuple | None:
    """``(entity_type, primary key)``, or None if the flush gave it no key."""
    primary = inspect(obj).mapper.primary_key_from_instance(obj)[0]
    return None if primary is None else (entity_type_of(type(obj)), primary)


def _new_entry(session, action, entity_type, record_id, entity_name, changes, details=None):
    from app.models.audit_log import AuditLog

    actor = session.info.get(ACTOR_KEY) or {}
    return AuditLog(
        user_id=actor.get("id"),
        user_name=actor.get("name") or SYSTEM_USER_NAME,
        user_username=actor.get("username"),
        action=action,
        entity_type=entity_type,
        entity_id=record_id if isinstance(record_id, int) else None,
        entity_name=entity_name,
        changes=changes,
        details=details,
    )


def _merge_later_change(entry, changes: dict) -> None:
    """Fold a second flush of the same record into its entry: the first old
    value and the last new one."""
    merged = dict(entry.changes or {})
    for key, change in changes.items():
        merged[key] = {"old": merged[key]["old"], "new": change["new"]} if key in merged else change
    entry.changes = merged


def _write_entry(session, state: _CaptureState, record_key: tuple, captured: _Captured, changes: dict) -> None:
    explicit = state.explicit.get(record_key)
    if explicit is not None:
        explicit.changes = {**(explicit.changes or {}), **changes}
        return
    earlier = state.automatic.get(record_key)
    if earlier is not None and captured.action != DELETE:
        _merge_later_change(earlier, changes)
        return
    entry = _new_entry(session, captured.action, record_key[0], record_key[1], captured.entity_name, changes)
    session.add(entry)
    state.automatic[record_key] = entry


def add_explicit_entry(session, entry) -> None:
    """Add a ``log_action`` entry, taking the place of the automatic entry for
    the same record if this transaction has one. A flush still to come merges
    into it the same way. Field values from the automatic entry win, since they
    come from the row itself."""
    state = _state(session)
    record = entry.entity_id if entry.entity_id is not None else entry.entity_name
    record_key = None if record is None else (entry.entity_type, record)
    automatic = state.automatic.pop(record_key, None)
    if automatic is None:
        session.add(entry)
        target = entry
    else:
        for attr in ("user_id", "user_name", "user_username", "action", "ip_address", "details"):
            setattr(automatic, attr, getattr(entry, attr))
        automatic.entity_name = entry.entity_name or automatic.entity_name
        automatic.changes = {**(entry.changes or {}), **(automatic.changes or {})}
        target = automatic
    if record_key is not None:
        state.explicit[record_key] = target


def _collect(session, state: _CaptureState, objects, action: str) -> None:
    for obj in objects:
        if not _is_captured(obj, state.run):
            continue
        changes = None
        if action == UPDATE:
            changes = _update_changes(session, obj)
        elif action == DELETE:
            changes = _delete_changes(obj)
        state.pending.append(_Captured(obj, action, _entity_name(obj), changes))


def _before_flush(session, _flush_context, _instances) -> None:
    state = _state(session)
    _collect(session, state, session.new, CREATE)
    _collect(session, state, session.dirty, UPDATE)
    _collect(session, state, session.deleted, DELETE)


def _settle(captured: _Captured) -> tuple[str, dict]:
    """Final action and changes, now that the flush has run. Removing a child
    from a delete-orphan parent looks like an update until the flush deletes it."""
    obj_state = inspect(captured.obj)
    if captured.action == UPDATE and obj_state.was_deleted:
        return DELETE, _delete_changes(captured.obj)
    if captured.action == CREATE:
        return CREATE, _create_changes(captured.obj)
    return captured.action, captured.changes


def _after_flush_postexec(session, _flush_context) -> None:
    state = _state(session)
    pending, state.pending = state.pending, []
    for captured in pending:
        action, changes = _settle(captured)
        record_key = _record_key(captured.obj)
        if record_key is None or (action == UPDATE and not changes):
            continue
        if state.run is not None:
            state.run.tally(type(captured.obj).__name__, action, record_key[1])
            continue
        captured.action = action
        _write_entry(session, state, record_key, captured, changes)
    if state.run is not None:
        _refresh_run_entry(session, state.run)


def _refresh_run_entry(session, run: _MachineRun) -> None:
    if not run.stale:
        return
    run.stale = False
    if run.entry is None:
        run.entry = _new_entry(session, run.action, run.entity_type, None, None, run.summary(), run.details)
        session.add(run.entry)
    else:
        run.entry.changes = run.summary()


def _after_transaction_create(session, transaction) -> None:
    run = _state(session).run
    if run is not None and transaction.nested:
        run.frames.append({})


def _after_commit(session) -> None:
    run = _state(session).run
    if run is None:
        return
    if session.in_nested_transaction():
        run.merge_top_frame()
    else:
        while len(run.frames) > 1:
            run.merge_top_frame()
        run.frames.append({})


def _after_rollback(session) -> None:
    run = _state(session).run
    if run is None:
        return
    if session.in_nested_transaction():
        run.frames.pop()
    else:
        run.frames[1:] = [{}]
    run.stale = True


def _after_soft_rollback(session, _previous_transaction) -> None:
    """Forget what the rollback removed from the session. An entry queued by a
    flush that failed goes with the rest."""
    state = _state(session)
    state.pending.clear()
    for entries in (state.automatic, state.explicit):
        for record_key in [key for key, entry in entries.items() if entry not in session]:
            del entries[record_key]
    if state.run is not None and state.run.entry is not None and state.run.entry not in session:
        state.run.entry = None


def _after_transaction_end(session, transaction) -> None:
    if transaction.parent is None:
        state = _state(session)
        state.automatic.clear()
        state.explicit.clear()


def install(sessionmaker) -> None:
    """Turn on capture for every session this factory makes."""
    event.listen(sessionmaker, "before_flush", _before_flush)
    event.listen(sessionmaker, "after_flush_postexec", _after_flush_postexec)
    event.listen(sessionmaker, "after_transaction_create", _after_transaction_create)
    event.listen(sessionmaker, "after_commit", _after_commit)
    event.listen(sessionmaker, "after_rollback", _after_rollback)
    event.listen(sessionmaker, "after_soft_rollback", _after_soft_rollback)
    event.listen(sessionmaker, "after_transaction_end", _after_transaction_end)


@contextmanager
def machine_run(session, action: str, entity_type: str, details: str | None = None):
    """Record the writes in this block as one summary entry, not one per row.

    The row joins the session's transaction and is kept current at each flush,
    so each batch the block commits is on record along with the counts so far.
    Commit after the block for anything it left uncommitted, as with
    ``log_action``. If the block raises, what it committed stays reported and
    capture resumes. A run inside a run counts toward the outer one. Other
    sessions are not affected, so a person's edit during a sync is still logged
    in full.
    """
    state = _state(session)
    if state.run is not None:
        yield
        return
    run = _MachineRun(action, entity_type, details)
    state.run = run
    try:
        yield
        session.flush()
        run.stale = run.stale or run.entry is None
        _refresh_run_entry(session, run)
    finally:
        state.run = None
