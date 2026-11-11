"""Turn a database integrity error into a reply that names the field.

SQLite names the column of a NOT NULL failure but not of a FOREIGN KEY one, so
for an INSERT or UPDATE the failed statement is read back: each foreign-key
column it wrote is checked against the table it points at, and the first value
with no row there is the one named. Anything else (a UNIQUE clash, a delete of
a row still in use, a statement this cannot read) stays a 409 conflict.
"""

import re

from sqlalchemy import text

CONFLICT = ("This change conflicts with other records: it is still in use elsewhere, "
            "or duplicates an existing entry.")

_NOT_NULL = "NOT NULL constraint failed:"
_FOREIGN_KEY = "FOREIGN KEY constraint failed"
# Column and placeholder lists hold no ")", so negated classes match them
# without backtracking.
_INSERT = re.compile(r'^\s*INSERT INTO "?(\w+)"? \(([^)]*)\) VALUES \(([^)]*)\)', re.IGNORECASE)
_UPDATE = re.compile(r'^\s*UPDATE "?(\w+)"? SET ', re.IGNORECASE)
_WHERE = re.compile(r'\sWHERE\s', re.IGNORECASE)


def _bound_columns(statement: str) -> tuple[str | None, list[str], bool]:
    """(table, the column of each ? placeholder in order, is_insert), or
    (None, [], False) when the statement is not a plain INSERT or UPDATE."""
    m = _INSERT.match(statement)
    if m:
        columns = [c.strip().strip('"') for c in m.group(2).split(",")]
        values = [v.strip() for v in m.group(3).split(",")]
        if len(columns) != len(values):
            return None, [], False
        return m.group(1), [c for c, v in zip(columns, values) if v == "?"], True
    m = _UPDATE.match(statement)
    where = _WHERE.search(statement, m.end()) if m else None
    if m and where:
        pairs = [p.split("=", 1) for p in statement[m.end():where.start()].split(",")]
        if any(len(p) != 2 for p in pairs):
            return None, [], False
        return m.group(1), [c.strip().strip('"') for c, v in pairs if v.strip() == "?"], False
    return None, [], False


def _written_rows(columns: list[str], params, is_insert: bool) -> list[dict]:
    """The values each written row gave its columns. A multi-row INSERT sends
    one flat tuple; an UPDATE's tuple ends with its WHERE values."""
    batches = params if isinstance(params, list) else [params]
    rows = []
    for batch in batches:
        flat = list(batch or ())
        starts = range(0, len(flat), len(columns)) if is_insert else [0]
        rows.extend(dict(zip(columns, flat[i:i + len(columns)])) for i in starts)
    return rows


def missing_reference(engine, metadata, statement: str, params) -> tuple[str, object] | None:
    """(column, value) of the first foreign key the statement wrote that
    points at no row, or None."""
    table_name, columns, is_insert = _bound_columns(statement or "")
    table = metadata.tables.get(table_name or "")
    if table is None or not columns:
        return None
    with engine.connect() as conn:
        for row in _written_rows(columns, params, is_insert):
            for column, value in row.items():
                if value is None or column not in table.c:
                    continue
                for fk in table.c[column].foreign_keys:
                    target = fk.column
                    found = conn.execute(
                        text(f'SELECT 1 FROM "{target.table.name}" WHERE "{target.name}" = :v LIMIT 1'),
                        {"v": value},
                    ).first()
                    if found is None:
                        return column, value
    return None


def integrity_reply(engine, metadata, exc) -> tuple[int, str]:
    """(status, detail) for an IntegrityError: 422 naming the column for a
    missing required value or an unknown reference, else 409."""
    message = str(exc.orig)
    if message.startswith(_NOT_NULL):
        column = message[len(_NOT_NULL):].strip().rsplit(".", 1)[-1]
        return 422, f"{column} is required"
    if _FOREIGN_KEY in message:
        try:
            bad = missing_reference(engine, metadata, exc.statement, exc.params)
        except Exception:
            bad = None
        if bad:
            column, value = bad
            return 422, f"{column} {value} does not exist"
    return 409, CONFLICT
