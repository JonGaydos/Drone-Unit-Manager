"""AUTOINCREMENT on every table, so ids are never reused

SQLite without AUTOINCREMENT gives a new row max(id) + 1, so deleting the newest
row frees its id for the next insert, and audit entries that name the deleted
record then point at an unrelated one. SQLite cannot add AUTOINCREMENT to an
existing table, so each table with a single integer primary key is rebuilt in
batch mode: rows, ids, indexes and foreign keys are copied as they are. The
sequence starts at the table's current highest id.

Revision ID: 0014_autoincrement_ids
Revises: 0013_clean_flight_battery_serials
Create Date: 2026-11-08 12:00:00.000000

"""
from typing import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0014_autoincrement_ids'
down_revision: str | None = '0013_clean_flight_battery_serials'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SKIP = ("alembic_version", "sqlite_sequence")


def _integer_key_tables(conn, with_autoincrement: bool) -> list[str]:
    """Tables keyed by one integer column whose AUTOINCREMENT state matches."""
    inspector = sa.inspect(conn)
    tables = []
    for table in inspector.get_table_names():
        if table in SKIP or table.startswith("_alembic_tmp"):
            continue
        pk = inspector.get_pk_constraint(table)["constrained_columns"]
        if len(pk) != 1:
            continue
        column = next(c for c in inspector.get_columns(table) if c["name"] == pk[0])
        if not isinstance(column["type"], sa.Integer):
            continue
        sql = conn.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).scalar() or ""
        if ("AUTOINCREMENT" in sql.upper()) == with_autoincrement:
            tables.append(table)
    return tables


def _rebuild(autoincrement: bool) -> None:
    conn = op.get_bind()
    if conn.dialect.name != "sqlite":
        return
    # Rebuilding drops each table. With foreign keys enforced that drop would
    # cascade into, or be refused by, the child tables. Alembic's own
    # connection never turns them on; refuse rather than lose rows if it did.
    if conn.exec_driver_sql("PRAGMA foreign_keys").scalar():
        raise RuntimeError("0014_autoincrement_ids must run with PRAGMA foreign_keys=OFF")
    for table in _integer_key_tables(conn, with_autoincrement=not autoincrement):
        with op.batch_alter_table(table, recreate="always",
                                  table_kwargs={"sqlite_autoincrement": autoincrement}):
            pass


def upgrade() -> None:
    _rebuild(autoincrement=True)


def downgrade() -> None:
    _rebuild(autoincrement=False)
