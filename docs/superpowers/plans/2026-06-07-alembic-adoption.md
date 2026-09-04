# Alembic Adoption (main DB) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** Put the main DB under Alembic (replace startup `create_all` + hand-rolled `run_migrations` for the main DB), with a verified schema-parity check. Telemetry DB unchanged. Rollout is fresh-build + re-import (no stamp).

**Tech:** alembic 1.14.1 (already in requirements). Backend python `D:/Claude Projects/Drone-Unit-Manager/backend/.venv/Scripts/python.exe`; run alembic via `.venv/Scripts/python.exe -m alembic` from the `backend` dir with `PYTHONPATH=.`.

**Branch:** `feat/alembic-adoption`.

**Key facts (verify):** `Base`/`engine` (main) + `TelemetryBase`/`telemetry_engine` (telemetry) in `app/database.py`; `app/models/__init__.py` imports ALL models so `Base.metadata` is complete; `TelemetryPoint` is on `TelemetryBase` (so it's excluded from `Base.metadata` — main migration must NOT include `telemetry_points`). SQLite → Alembic must use `render_as_batch=True`. Dockerfile currently `COPY backend/app ./app` only.

---

### Task 0: Branch
- [ ] `git -C "D:/Claude Projects/Drone-Unit-Manager" checkout main && git -C "..." pull --ff-only && git -C "..." checkout -b feat/alembic-adoption`

### Task 1: Scaffold Alembic wired to the app
**Files:** create `backend/alembic.ini`, `backend/migrations/env.py`, `backend/migrations/script.py.mako`, `backend/migrations/versions/` (empty dir + `.gitkeep`).

- [ ] **alembic.ini** — minimal: `[alembic]` with `script_location = migrations`, a `[loggers]/[handlers]/[formatters]` block (standard). Do NOT hard-code `sqlalchemy.url` (env.py supplies it).
- [ ] **env.py** — wire to the app:
```python
from logging.config import fileConfig
from alembic import context
from app.config import settings
from app.database import Base
import app.models  # noqa: F401  -- populate Base.metadata with every table

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
target_metadata = Base.metadata

def run_migrations_offline():
    context.configure(url=settings.DATABASE_URL, target_metadata=target_metadata,
                      literal_binds=True, render_as_batch=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    from sqlalchemy import engine_from_config, pool
    cfg = config.get_section(config.config_ini_section)
    connectable = engine_from_config(cfg, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata,
                          render_as_batch=True, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```
- [ ] **script.py.mako** — the standard Alembic template (copy the default).
- [ ] Verify env imports: `cd backend && PYTHONPATH=. .venv/Scripts/python.exe -m alembic -c alembic.ini current` runs without error (prints nothing/base on a DB, or creates none). It must import cleanly.
- [ ] Commit.

### Task 2: Generate the baseline migration
- [ ] Point at a TEMP fresh sqlite (so autogenerate diffs models vs an empty DB → full create):
```bash
cd "D:/Claude Projects/Drone-Unit-Manager/backend"
DATABASE_URL="sqlite:///C:/Users/jgayd/.claude/plans/alembic_tmp.db" PYTHONPATH=. .venv/Scripts/python.exe -m alembic -c alembic.ini revision --autogenerate -m "baseline schema"
```
(env.py reads `settings.DATABASE_URL`; ensure the env var is honored — settings reads env. If settings caches, instead temporarily set the URL via the env var BEFORE import.)
- [ ] **Review the generated `versions/*_baseline*.py`**: it must `op.create_table(...)` for every main-DB table (users, pilots, vehicles, flights, ... calendar_events, etc.) and create the model-declared indexes. It must NOT include `telemetry_points` (that's TelemetryBase). Rename the file/revision id to a clear `0001_baseline`. Delete the temp db.
- [ ] Commit the baseline.

### Task 3: Schema-parity verification (the gate)
- [ ] Temp script `C:/Users/jgayd/.claude/plans/alembic_parity.py`: build DB-A via `Base.metadata.create_all`, DB-B via `alembic upgrade head` (programmatic `command.upgrade`), then compare: set of tables (exclude `alembic_version`), and for each table the `PRAGMA table_info` (name, type, notnull, pk) and the index list (`PRAGMA index_list` + `index_info`). Assert equal; print `PARITY_OK` or the diff.
```bash
cd "D:/Claude Projects/Drone-Unit-Manager/backend" && PYTHONPATH=. .venv/Scripts/python.exe "C:/Users/jgayd/.claude/plans/alembic_parity.py"
```
- [ ] If diffs: edit the baseline migration to match `create_all` exactly, re-run until `PARITY_OK`. Then delete the temp script. (Common SQLite/autogenerate diffs: server defaults, boolean rendering, index names — reconcile to the create_all output.) Commit any baseline fixes.

### Task 4: Lifespan — run Alembic for the main DB
**File:** `backend/app/main.py` (lifespan). Replace the main-DB `Base.metadata.create_all(bind=engine)` and the main-DB `run_migrations()` call with a programmatic upgrade; KEEP telemetry create_all + seed order.
```python
    # Main DB schema via Alembic
    from alembic.config import Config
    from alembic import command
    from pathlib import Path
    _ini = Path(__file__).resolve().parent.parent / "alembic.ini"
    cfg = Config(str(_ini))
    cfg.set_main_option("script_location", str(_ini.parent / "migrations"))
    cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    command.upgrade(cfg, "head")
    # Telemetry DB (unchanged)
    TelemetryBase.metadata.create_all(bind=telemetry_engine)
    from app.services.migrations import run_telemetry_migrations
    run_telemetry_migrations()
    seed_defaults()
    ...
```
(`Path(__file__).parent.parent` = backend in dev, /app in container — matches where Task 6 copies alembic.ini.) Keep `import app.models` reachable (it is, via routers). Verify `settings` and `TelemetryBase`/`telemetry_engine` are imported in main.py (they are).

### Task 5: Slim services/migrations.py to telemetry-only
**File:** `backend/app/services/migrations.py`.
- [ ] First verify whether `TelemetryPoint` (models/telemetry.py) declares `extra_data` and `source`. If YES → telemetry `create_all` builds them and you can drop `run_migrations` entirely (and the lifespan telemetry-migration call). If NO → keep ONLY the telemetry-DB migration block as `run_telemetry_migrations()` and remove the main-DB migration list, index list, and the has_telemetry backfill.
- [ ] Remove the now-unused main-DB `migrations` list, `_apply_index_migrations` main-DB call, and the has_telemetry backfill (the refresh-path code fix in flights.py stays). Keep `_apply_column_migrations`/`_apply_index_migrations` helpers only if still used by telemetry.
- [ ] py_compile + `import app.main`.
- [ ] Commit (lifespan + migrations slim together).

### Task 6: Dockerfile — ship the migrations into the image
**File:** `Dockerfile`. After `COPY backend/app ./app`, add:
```dockerfile
COPY backend/migrations ./migrations
COPY backend/alembic.ini ./alembic.ini
```
So at runtime (`WORKDIR /app`) the ini is `/app/alembic.ini` and scripts at `/app/migrations` — matching the lifespan path (`Path(__file__).parent.parent` = `/app`). Commit.

### Task 7: Verify end-to-end
- [ ] `cd backend && PYTHONPATH=. .venv/Scripts/python.exe -c "import app.main; print('IMPORT_OK')"`.
- [ ] Fresh-DB build: point DATABASE_URL at a temp path, start the app import (or run the lifespan upgrade path) → schema built; a trivial query (e.g. `select 1`/list a table) works. Re-run `alembic upgrade head` → clean no-op (`PARITY_OK` already covers schema match).
- [ ] Confirm the parity test still passes after Tasks 4-5.
- [ ] (No Docker build locally; CI verifies the image build — ensure the COPY lines are correct.)

### Task 8: Rollout notes (for the merge presentation, not a code step)
Reset `/app/data` (or delete `drone_unit_manager.db`) on Unraid, `docker compose pull && up -d` → Alembic builds the schema → seed → re-import (Skydio sync + CSV/Excel + re-enter API keys).

---

## Self-review (against spec)
- Main DB under Alembic; telemetry unchanged → Tasks 1-6. ✓
- Baseline = full current schema, excludes telemetry_points → Task 2. ✓
- Schema parity verified (create_all vs alembic) → Task 3 gate. ✓
- Lifespan migrate->seed order kept; has_telemetry backfill dropped → Tasks 4-5. ✓
- Dockerfile ships migrations/+alembic.ini → Task 6. ✓
- No stamp/adoption logic (fresh build) → by omission, rollout resets. ✓
- Risk: autogenerate schema drift — caught by the Task 3 parity gate before merge. ✓
