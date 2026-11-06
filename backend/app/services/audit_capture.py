"""Automatic audit capture: every ORM create, update and delete gets an entry.

A session hook writes the entries in the same transaction as the change, so
the change and its record commit together or not at all. ``log_action`` entries
take the place of the automatic entry for the same record. Inside
``machine_run`` the hook counts changes instead and keeps one summary row,
written at each commit. ``record_bulk`` records a query-level write, which
the hook cannot see.

The hook runs in three steps. ``before_flush`` reads old values while they are
still available, ``after_flush`` adds foreign keys the flush itself set, and
``after_flush_postexec`` writes entries once new rows have IDs.

Entries go straight through the transaction's connection rather than the
session. An object added to the session at this point would stay pending past
the flush, and rolling back a savepoint expunges everything pending, whether
or not it was queued inside that savepoint. Written this way, a failed audit
write fails the flush, and the session refuses to commit until rolled back.

This module is imported by ``app.database``, so it imports models and
``app.services.audit`` inside the functions that use them.
"""

import re
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from functools import cache

from sqlalchemy import event, func, inspect, select
from sqlalchemy.orm.attributes import PASSIVE_NO_INITIALIZE, set_committed_value

from app.constants import SECRET_KEYS

ACTOR_KEY = "audit_actor"
_STATE_KEY = "audit_capture"

SYSTEM_USER_NAME = "System"
CREATE = "create"
UPDATE = "update"
DELETE = "delete"
_ACTIONS = (CREATE, UPDATE, DELETE)
# log_action verbs that mean the record is gone.
_DELETE_ACTIONS = frozenset({DELETE, "purge"})
# Old value of a key the flush overwrote before anything had loaded it.
_OLD_VALUE_UNKNOWN = "(unknown)"

_FOLDED_ATTR = "_audit_folded"
_AUDIT_LOG_MODEL = "AuditLog"
_SETTING_MODEL = "Setting"
_SETTING_VALUE_FIELD = "value"

EXCLUDED_MODELS = frozenset({_AUDIT_LOG_MODEL, "NotificationLog", "Alert"})
# Bookkeeping, plus theme, a personal display preference, and the path of a
# thumbnail the server builds on its own.
EXCLUDED_FIELDS = frozenset({
    "created_at", "updated_at", "last_used_at", "token_version", "modified_by_id", "theme",
    "thumbnail_path",
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
    examined: frozenset = frozenset()


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
    entry_id: int | None = None
    committed_entry_id: int | None = None
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


@dataclass(frozen=True)
class _Tracked:
    """The audit row standing for one record in this transaction. ``settled``
    is False for a ``log_action`` entry still waiting for its flush, which has
    ``orm_entry`` and no ``entry_id`` until then."""
    entry_id: int | None
    action: str
    changes: dict
    explicit: bool
    settled: bool
    orm_entry: object = None


@dataclass
class _CaptureState:
    """``savepoints`` holds, per open savepoint, what to go back to if it rolls
    back: ``records`` and the run's row as they were when it began."""
    pending: list = field(default_factory=list)
    records: dict = field(default_factory=dict)
    unsettled: list = field(default_factory=list)
    savepoints: list = field(default_factory=list)
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


def actor_fields(user) -> dict:
    """Who a user is, in plain values that can outlive the user's session."""
    return {"id": user.id, "name": user.display_name, "username": user.username}


def set_actor(session, user) -> None:
    """Record who is acting on this session, for every entry written through it.
    ``user`` is a user, or what ``actor_fields`` returned for one."""
    session.info[ACTOR_KEY] = user if isinstance(user, dict) else actor_fields(user)


@cache
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
    if name == _AUDIT_LOG_MODEL or getattr(obj, _FOLDED_ATTR, False) or _is_status_setting(obj):
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


@cache
def _recorded_keys(mapper) -> tuple:
    """Column attributes an entry may mention: not the key, not bookkeeping."""
    primary = {column.key for column in mapper.primary_key}
    return tuple(
        attr.key for attr in mapper.column_attrs
        if attr.key not in EXCLUDED_FIELDS and attr.columns[0].key not in primary
    )


def _history_if_changed(obj_state, key: str):
    """The attribute's history if it has changes, else None. Only an attribute
    in ``committed_state`` can have any, so most need no history at all. Building
    ``obj_state.attrs`` instead costs an object per attribute per row."""
    if key not in obj_state.committed_state:
        return None
    history = obj_state.get_history(key, PASSIVE_NO_INITIALIZE)
    return history if history.has_changes() else None


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
        history = _history_if_changed(obj_state, key)
        if history is not None:
            new = history.added[0] if history.added else None
            pairs[key] = (history.deleted[0] if history.deleted else None, new)
            if not history.deleted:
                old_unknown.append(key)
    if old_unknown:
        stored = _stored_values(session, obj_state, old_unknown)
        pairs.update({key: (stored.get(key), pairs[key][1]) for key in old_unknown})
    return pairs


def _update_changes(obj, pairs: dict) -> dict:
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
    obj_state = inspect(obj)
    # The identity needs no query. Reading the key off an expired object would.
    primary = obj_state.identity[0] if obj_state.identity else obj_state.mapper.primary_key_from_instance(obj)[0]
    return None if primary is None else (entity_type_of(type(obj)), primary)


def _row_values(session, action, entity_type, record_id, entity_name, changes, details=None) -> dict:
    actor = session.info.get(ACTOR_KEY) or {}
    return {
        "user_id": actor.get("id"),
        "user_name": actor.get("name") or SYSTEM_USER_NAME,
        "user_username": actor.get("username"),
        "action": action,
        "entity_type": entity_type,
        "entity_id": record_id if isinstance(record_id, int) else None,
        "entity_name": entity_name,
        "changes": changes,
        "details": details,
    }


def _audit_table():
    from app.models.audit_log import AuditLog

    return AuditLog.__table__


def _insert_row(session, values: dict) -> int:
    # Values as parameters, not on the statement, so all rows share one compiled form.
    result = session.connection().execute(_audit_table().insert(), values)
    return result.inserted_primary_key[0]


def _insert_rows(session, rows: list[dict]) -> range:
    """Insert one row at a time in a single executemany, and return their IDs in
    order. Each new row takes one more than the largest ID in use, and this
    transaction now holds SQLite's write lock, so the last ID gives all of them."""
    table = _audit_table()
    connection = session.connection()
    connection.execute(table.insert(), rows)
    last_id = connection.execute(select(func.max(table.c.id))).scalar_one()
    return range(last_id - len(rows) + 1, last_id + 1)


def _update_row(session, entry_id: int, values: dict) -> None:
    table = _audit_table()
    session.connection().execute(table.update().where(table.c.id == entry_id).values(**values))


def _delete_row(session, entry_id: int) -> None:
    table = _audit_table()
    session.connection().execute(table.delete().where(table.c.id == entry_id))


def _can_merge(earlier: _Tracked, action: str) -> bool:
    """Whether a captured change belongs to the entry already standing for its
    record. A record's ID can come back for a new row after a delete, so a
    settled delete takes nothing further, and a delete always gets its own
    entry. A delete logged before its flush takes the change it announced,
    which for a soft delete is an update."""
    if earlier.action in _DELETE_ACTIONS:
        return not earlier.settled and action != CREATE
    return action != DELETE


def _merged_changes(earlier: _Tracked, changes: dict) -> dict:
    """Changes after folding in a later flush. An entry logged before this flush
    has not seen the row, so the captured values win. An entry that has keeps
    its first old value; a field back at that value drops out."""
    if not earlier.settled:
        return {**earlier.changes, **changes}
    merged = dict(earlier.changes)
    for key, change in changes.items():
        prior = merged.get(key)
        # log_action callers may pass plain values, with no old value to keep.
        if not (isinstance(prior, dict) and "old" in prior) or change["new"] == SECRET_MARKER:
            merged[key] = change
        elif prior["old"] == change["new"]:
            del merged[key]
        else:
            merged[key] = {"old": prior["old"], "new": change["new"]}
    return merged


def _merge_into(session, state: _CaptureState, record_key: tuple, earlier: _Tracked, changes: dict) -> None:
    merged = _merged_changes(earlier, changes)
    entry_id = earlier.entry_id if earlier.settled else earlier.orm_entry.id
    if not merged and earlier.action == UPDATE and not earlier.explicit:
        _delete_row(session, entry_id)
        del state.records[record_key]
        return
    _update_row(session, entry_id, {"changes": merged})
    if earlier.orm_entry is not None:
        set_committed_value(earlier.orm_entry, "changes", merged)
    state.records[record_key] = replace(earlier, changes=merged)


def _write_entry(session, state: _CaptureState, record_key: tuple, captured: _Captured, changes: dict) -> None:
    earlier = state.records.get(record_key)
    if earlier is not None and _can_merge(earlier, captured.action):
        _merge_into(session, state, record_key, earlier, changes)
        return
    entry_id = _insert_row(session, _row_values(
        session, captured.action, record_key[0], record_key[1], captured.entity_name, changes))
    state.records[record_key] = _Tracked(entry_id, captured.action, changes, explicit=False, settled=True)


def _write_batch(session, state: _CaptureState, batch: list) -> None:
    """Write entries for records with none yet in this transaction."""
    if not batch:
        return
    rows = [
        _row_values(session, captured.action, record_key[0], record_key[1], captured.entity_name, changes)
        for record_key, captured, changes in batch
    ]
    for entry_id, (record_key, captured, changes) in zip(_insert_rows(session, rows), batch):
        state.records[record_key] = _Tracked(entry_id, captured.action, changes, explicit=False, settled=True)
    batch.clear()


def _write_entries(session, state: _CaptureState, entries: list) -> None:
    """Write ``(record key, captured, changes)`` entries in order, batching those
    for records with no entry yet. A record that has one, or has one waiting in
    the batch, needs that entry's ID, so the batch goes first and the statements
    stay in the order of the entries."""
    batch: list = []
    batched_keys = set()
    for record_key, captured, changes in entries:
        if record_key in state.records or record_key in batched_keys:
            _write_batch(session, state, batch)
            batched_keys.clear()
            _write_entry(session, state, record_key, captured, changes)
        else:
            batch.append((record_key, captured, changes))
            batched_keys.add(record_key)
    _write_batch(session, state, batch)


def _absorb(session, state: _CaptureState, record_key: tuple, automatic: _Tracked, entry) -> None:
    """Turn an automatic entry into this ``log_action`` entry. Field values from
    the automatic entry win, since they come from the row itself."""
    merged = {**(entry.changes or {}), **automatic.changes}
    values = {attr: getattr(entry, attr) for attr in (
        "user_id", "user_name", "user_username", "action", "ip_address", "details")}
    values["changes"] = merged
    if entry.entity_name:
        values["entity_name"] = entry.entity_name
    _update_row(session, automatic.entry_id, values)
    state.records[record_key] = replace(automatic, action=entry.action, changes=merged, explicit=True)


def add_explicit_entry(session, entry) -> None:
    """Add a ``log_action`` entry, taking the place of the automatic entry for
    the same record if this transaction has one. A delete only takes the place
    of a delete, and anything else only of a create or update. A flush still to
    come merges into this entry under the same rule."""
    state = _state(session)
    record = entry.entity_id if entry.entity_id is not None else entry.entity_name
    record_key = None if record is None else (entry.entity_type, record)
    earlier = state.records.get(record_key)
    if (earlier is not None and not earlier.explicit
            and (earlier.action in _DELETE_ACTIONS) == (entry.action in _DELETE_ACTIONS)):
        _absorb(session, state, record_key, earlier, entry)
        return
    session.add(entry)
    if record_key is not None:
        state.records[record_key] = _Tracked(
            None, entry.action, entry.changes or {}, explicit=True, settled=False, orm_entry=entry)
        state.unsettled.append(record_key)


def _load_keys_a_flush_will_set(obj_state) -> None:
    """Read a foreign key the flush will set from a changed relationship. If it
    has expired the flush overwrites it, and its old value is gone."""
    mapper = obj_state.mapper
    for relationship in mapper.relationships:
        if _history_if_changed(obj_state, relationship.key) is not None:
            for column in relationship.local_columns:
                getattr(obj_state.obj(), mapper.get_property_by_column(column).key)


def _counts_as_update(obj) -> bool:
    """Whether a run counts this object as updated. Reads only what is in memory,
    so a value set while expired counts even if it matches the stored one."""
    obj_state = inspect(obj)
    for key in _recorded_keys(obj_state.mapper):
        history = _history_if_changed(obj_state, key)
        if history is None:
            continue
        new = history.added[0] if history.added else None
        if not history.deleted or str(history.deleted[0]) != str(new):
            return True
    return False


def _collect_for_run(run, objects, action: str) -> list:
    """A run keeps counts, not values, and spends no query per row finding them."""
    return [
        _Captured(obj, action, None, {})
        for obj in objects
        if _is_captured(obj, run) and (action != UPDATE or _counts_as_update(obj))
    ]


def _collect(session, run, objects, action: str) -> list:
    if run is not None:
        return _collect_for_run(run, objects, action)
    collected = []
    for obj in objects:
        if not _is_captured(obj, run):
            continue
        changes, examined = None, frozenset()
        if action == UPDATE:
            _load_keys_a_flush_will_set(inspect(obj))
            pairs = _changed_values(session, inspect(obj))
            changes, examined = _update_changes(obj, pairs), frozenset(pairs)
        elif action == DELETE:
            changes = _delete_changes(obj)
        collected.append(_Captured(obj, action, _entity_name(obj), changes, examined))
    return collected


def _before_flush(session, _flush_context, _instances) -> None:
    state = _state(session)
    # Assigned only when complete, so a failure here leaves nothing behind.
    state.pending = [
        *_collect(session, state.run, session.new, CREATE),
        *_collect(session, state.run, session.dirty, UPDATE),
        *_collect(session, state.run, session.deleted, DELETE),
    ]


def _flush_set_changes(obj, examined: frozenset) -> dict:
    """Changes the flush itself made, such as a foreign key synced from a
    relationship or cleared when its parent was deleted."""
    obj_state = inspect(obj)
    changes = {}
    for key in _recorded_keys(obj_state.mapper):
        history = None if key in examined else _history_if_changed(obj_state, key)
        if history is None:
            continue
        old = history.deleted[0] if history.deleted else _OLD_VALUE_UNKNOWN
        new = history.added[0] if history.added else None
        if str(old) != str(new):
            changes[key] = _format(obj, key, old, new)
    return changes


def _after_flush(session, _flush_context) -> None:
    """Add what only exists now. Until the flush finalizes, history still shows
    the state before it, with the synced foreign keys in place."""
    state = _state(session)
    by_object = {id(captured.obj): captured for captured in state.pending}
    for obj in session.dirty:
        if not _is_captured(obj, state.run):
            continue
        captured = by_object.get(id(obj))
        if captured and state.run is not None:
            continue
        changes = _flush_set_changes(obj, captured.examined if captured else frozenset())
        if changes and captured:
            captured.changes = {**captured.changes, **changes}
        elif changes:
            state.pending.append(_Captured(obj, UPDATE, _entity_name(obj), changes))


def _settle(captured: _Captured) -> tuple[str, dict]:
    """Final action and changes, now that the flush has run. Removing a child
    from a delete-orphan parent looks like an update until the flush deletes it."""
    obj_state = inspect(captured.obj)
    if captured.action == UPDATE and obj_state.was_deleted:
        return DELETE, _delete_changes(captured.obj)
    if captured.action == CREATE:
        return CREATE, _create_changes(captured.obj)
    return captured.action, captured.changes


def _settle_explicit_entries(state: _CaptureState) -> None:
    """Entries ``log_action`` queued have reached the database with this flush."""
    for record_key in state.unsettled:
        tracked = state.records.get(record_key)
        if tracked is not None and not tracked.settled:
            state.records[record_key] = replace(tracked, entry_id=tracked.orm_entry.id, settled=True)
    state.unsettled.clear()


def _after_flush_postexec(session, _flush_context) -> None:
    state = _state(session)
    pending, state.pending = state.pending, []
    if state.run is not None:
        _tally_flush(state.run, pending)
    else:
        entries = []
        for captured in pending:
            action, changes = _settle(captured)
            record_key = _record_key(captured.obj)
            if record_key is None or (action == UPDATE and not changes):
                continue
            captured.action = action
            entries.append((record_key, captured, changes))
        _write_entries(session, state, entries)
    _settle_explicit_entries(state)


def _tally_flush(run: _MachineRun, pending: list) -> None:
    for captured in pending:
        record_key = _record_key(captured.obj)
        if record_key is None:
            continue
        action = captured.action
        if action == UPDATE and inspect(captured.obj).was_deleted:
            action = DELETE
        run.tally(type(captured.obj).__name__, action, record_key[1])


def _refresh_run_entry(session, run: _MachineRun) -> None:
    if not run.stale:
        return
    summary = run.summary()
    if run.entry_id is not None:
        _update_row(session, run.entry_id, {"changes": summary})
    elif summary:
        run.entry_id = _insert_row(session, _row_values(
            session, run.action, run.entity_type, None, None, summary, run.details))
    # Last, so a commit after a failed write tries it again.
    run.stale = False


def _before_commit(session) -> None:
    """Bring a run's row up to date in the transaction about to commit. Only
    here, not at each flush: importers flush for every row, some in savepoints."""
    state = _state(session)
    if state.run is None or session.in_nested_transaction():
        return
    session.flush()
    _refresh_run_entry(session, state.run)


def _after_transaction_create(session, transaction) -> None:
    if not transaction.nested:
        return
    state = _state(session)
    state.savepoints.append((dict(state.records), state.run.entry_id if state.run else None))
    if state.run is not None:
        state.run.frames.append({})


def _after_commit(session) -> None:
    state = _state(session)
    nested = session.in_nested_transaction()
    if nested and state.savepoints:
        state.savepoints.pop()
    if state.run is None:
        return
    if nested:
        state.run.merge_top_frame()
    else:
        while len(state.run.frames) > 1:
            state.run.merge_top_frame()
        state.run.frames.append({})
        state.run.committed_entry_id = state.run.entry_id


def _after_rollback(session) -> None:
    """Put the tracking back where the database just went. A flush that failed
    leaves its captured objects behind too."""
    state = _state(session)
    state.pending = []
    state.unsettled.clear()
    nested = session.in_nested_transaction() and bool(state.savepoints)
    if nested:
        state.records, run_entry_id = state.savepoints.pop()
    else:
        state.records = {}
        state.savepoints.clear()
    if state.run is None:
        return
    if nested:
        state.run.frames.pop()
        state.run.entry_id = run_entry_id
    else:
        state.run.frames[1:] = [{}]
        state.run.entry_id = state.run.committed_entry_id
    state.run.stale = True


def _after_transaction_end(session, transaction) -> None:
    if transaction.parent is None:
        state = _state(session)
        state.records = {}
        state.unsettled.clear()
        state.savepoints.clear()


def install(sessionmaker) -> None:
    """Turn on capture for every session this factory makes."""
    event.listen(sessionmaker, "before_flush", _before_flush)
    event.listen(sessionmaker, "after_flush", _after_flush)
    event.listen(sessionmaker, "after_flush_postexec", _after_flush_postexec)
    event.listen(sessionmaker, "after_transaction_create", _after_transaction_create)
    event.listen(sessionmaker, "before_commit", _before_commit)
    event.listen(sessionmaker, "after_commit", _after_commit)
    event.listen(sessionmaker, "after_rollback", _after_rollback)
    event.listen(sessionmaker, "after_transaction_end", _after_transaction_end)


@contextmanager
def machine_run(session, action: str, entity_type: str, details: str | None = None):
    """Record the writes in this block as one summary entry, not one per row.

    The row joins the session's transaction and is brought current at each
    commit, so each batch the block commits is on record with the counts so far.
    A run that changes nothing writes no row.
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
        _refresh_run_entry(session, run)
    except BaseException:
        # What the block flushed is still in the transaction, for a caller that
        # commits anyway. It goes on record here, or does not stay.
        if session.is_active and any(run.frames[1:]):
            try:
                _refresh_run_entry(session, run)
            except Exception:
                session.rollback()
                raise
        raise
    finally:
        state.run = None


def _model_names() -> dict:
    """Class name for each ``entity_type``. Run summaries are keyed by class."""
    from app.database import Base

    return {entity_type_of(mapper.class_): mapper.class_.__name__ for mapper in Base.registry.mappers}


def _bulk_changes(ids: list[int], changes: dict | None) -> dict:
    """The record IDs in full, and as text in the ``new`` slot for the log page."""
    ordered = sorted(ids)
    shown = ordered[:MACHINE_RUN_ID_CAP]
    text = f"{len(ordered)} records: {', '.join(str(i) for i in shown)}"
    if len(ordered) > len(shown):
        text += f" (first {len(shown)} shown)"
    records = {"old": None, "new": text, "ids": ordered, "total_ids": len(ordered)}
    fields = {
        key: {"old": SECRET_MARKER, "new": SECRET_MARKER} if key in SECRET_FIELDS else change
        for key, change in (changes or {}).items()
    }
    return {"records": records, **fields}


def record_bulk(session, action: str, entity_type: str, ids: list[int], changes: dict | None) -> None:
    """Record a query-level write, which the session hook cannot see.

    Writes one entry in the session's transaction, or inside ``machine_run``
    adds the IDs to the run's counts. Call it with IDs read before the write.
    """
    if not ids:
        return
    run = _state(session).run
    if run is None:
        _insert_row(session, _row_values(session, action, entity_type, None, None, _bulk_changes(ids, changes)))
        return
    model = _model_names().get(entity_type, entity_type)
    for record_id in ids:
        run.tally(model, action, record_id)


def _query_model(query):
    return query.column_descriptions[0]["entity"]


def update_recorded(session, query, values: dict, action: str = UPDATE) -> int:
    """Run ``query.update`` and record it. ``values`` maps each column to its
    ``(old, new)`` pair, the same for every row. Returns how many rows matched."""
    from app.services.audit import _fmt_change

    model = _query_model(query)
    ids = [row[0] for row in query.with_entities(model.id)]
    if ids:
        query.update({column: new for column, (_, new) in values.items()}, synchronize_session=False)
        changes = {column.key: _fmt_change(old, new) for column, (old, new) in values.items()}
        record_bulk(session, action, entity_type_of(model), ids, changes)
    return len(ids)


def _delete_rows(query) -> tuple[str, list[int], str]:
    """Run ``query.delete``. Returns the entity type, the IDs and the values of
    each row, since the rows are gone after this."""
    model = _query_model(query)
    mapper = inspect(model)
    keys = _recorded_keys(mapper)
    rows = query.with_entities(model.id, *(mapper.get_property(key).columns[0] for key in keys)).all()
    if not rows:
        return entity_type_of(model), [], ""
    query.delete()
    traces = (
        f"{row[0]}: " + ", ".join(
            f"{key}={SECRET_MARKER if key in SECRET_FIELDS else value}"
            for key, value in zip(keys, row[1:]) if value is not None)
        for row in rows
    )
    return entity_type_of(model), [row[0] for row in rows], "; ".join(traces)


def delete_recorded(session, query) -> int:
    """Run ``query.delete`` and record it in an entry of its own. Returns how
    many rows matched."""
    entity_type, ids, trace = _delete_rows(query)
    record_bulk(session, DELETE, entity_type, ids, {"deleted": {"old": trace, "new": None}})
    return len(ids)


def delete_links(query) -> dict:
    """Run ``query.delete`` for link rows and return their record as ``changes``
    for the entry of the action that removed them, so the action stays one
    row. Empty if nothing matched."""
    entity_type, ids, trace = _delete_rows(query)
    if not ids:
        return {}
    return {entity_type: {"old": trace, "new": None, "ids": ids, "total_ids": len(ids)}}


def add_folded(session, obj) -> None:
    """Add a row whose record goes in the entry of the action that created it,
    so it gets no automatic entry of its own."""
    setattr(obj, _FOLDED_ATTR, True)
    session.add(obj)
