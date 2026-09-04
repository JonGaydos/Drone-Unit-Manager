# Backend Test Suite — Handoff Spec (for a fresh chat)

Date: 2026-06-10
Status: ready to build. Self-contained — a new session should be able to execute
this end-to-end. Read this fully first, plus skim
`docs/superpowers/plans/2026-06-10-pre-golive-master-plan.md` for context.

## Why
Drone Unit Manager (FastAPI + React, `D:\Claude Projects\Drone-Unit-Manager`)
has **no automated tests**. Every change has been verified with `py_compile` +
ad-hoc in-memory SQLite smoke scripts + manual clicks + a subagent reviewer.
Two production incidents (a login-500 from a column-default mismatch, a
dashboard React #31 from rendering an object) are exactly what a test suite
catches. Goal: a **pytest backend suite** covering the security- and
correctness-critical paths, wired into CI. Frontend (Vitest) is a LATER phase,
not this one.

## Environment / conventions
- Backend Python: `D:/Claude Projects/Drone-Unit-Manager/backend/.venv/Scripts/python.exe`.
  The venv is **uv-managed (no pip)** — install test deps with
  `uv pip install --python .venv/Scripts/python.exe pytest httpx`.
- Run from `backend/` with `PYTHONPATH=.`.
- App object: `app.main:app`. DB layer: `app/database.py` (`Base`/`engine`/
  `SessionLocal` for the main DB; `TelemetryBase`/`telemetry_engine`/
  `TelemetrySessionLocal` for telemetry). DB session dependency: find the
  `get_db` (and any telemetry session) dependency used by routers.
- Config: `app/config.py` `settings.DATABASE_URL` / `TELEMETRY_DATABASE_URL`
  (auto-generated from `DATA_DIR` if blank). `SECRET_KEY` from settings.
- Auth: `app/routers/auth.py` — `create_token(user_id)`, `get_current_user`,
  `require_admin` (`AdminUser`). Secret keys + redaction live in
  `app/routers/settings.py` (`SECRET_KEYS`, `REDACTED_MARKER`).
- Schema parity is already verified: `Base.metadata.create_all` == `alembic
  upgrade head`. Tests may build the schema with **create_all** for speed.
- Follow `git` discipline in CLAUDE.md: branch off main, subagent-driven-
  development sub-skill, merge `--ff-only`, push only when asked.

## Test infrastructure (build first)
Create `backend/tests/` with `conftest.py` providing fixtures:
- **Fresh DB per test** (or per module): point `settings.DATABASE_URL` +
  `TELEMETRY_DATABASE_URL` at temp SQLite files under `tmp_path` (a temp FILE is
  more robust than `:memory:` with TestClient threads; if using `:memory:`, use
  a shared `StaticPool` + `check_same_thread=False`). Create schema via
  `Base.metadata.create_all(engine)` + `TelemetryBase.metadata.create_all(
  telemetry_engine)` bound to the temp engines. Override the `get_db` (and
  telemetry session) dependency via `app.dependency_overrides`.
- **`client`**: `fastapi.testclient.TestClient(app)` with the overrides applied.
- **`db`**: a Session bound to the temp main engine for direct seed/asserts.
- **`admin_headers`**: seed an admin `User` (hashed password via the app's
  bcrypt helper), `create_token(user.id)`, return `{"Authorization": f"Bearer
  {token}"}`.
- **`pilot_headers`**: seed a non-admin user for role-gating tests.
- **External calls are MOCKED**: never hit the network. `monkeypatch` `httpx.get`
  for geocode/weather/adsb/sync tests; assert on the app's handling of mocked
  responses.

## Coverage priorities (one module each; assert the behavior, not the impl)
1. **test_auth.py** — login OK returns a token; wrong password / unknown user →
   401 (and comparable timing path doesn't 500); protected route without/with
   token → 401/200; **role gating**: an admin-only endpoint (e.g. `/audit`,
   `/settings/bulk`, `/sync/disconnect`) rejects `pilot_headers` with 403.
2. **test_settings.py** — GET redacts secrets (stored token → `********`);
   bulk-save with `""`/`********` for a secret key does NOT overwrite the stored
   value (the guard); a real new token IS saved; a non-secret key saves;
   non-allowlisted key ignored.
3. **test_sync.py** — `/sync/status` returns `last_sync_result` when the setting
   is present (and `None` when absent/garbage); `POST /sync/disconnect` clears
   `skydio_api_token`/`skydio_token_id` and is admin-gated (pilot → 403).
4. **test_flights.py** — create a flight; **bulk-delete** purges telemetry rows
   (separate DB) and nulls/deletes the FK references (incident.flight_id,
   media_files, checklist_completions, flight_plans.linked_flight_id) so the
   delete succeeds (no IntegrityError); single delete of a referenced flight
   works; **review_status** invalid value → 422; bulk-update authz.
5. **test_photos.py** — link/unlink requires supervisor (non-supervisor → 403);
   link to a nonexistent flight/incident → 404 (no dangling junction row);
   signed-URL: a valid HMAC+unexpired URL serves; tampered/expired → rejected.
6. **test_backup.py** — export JSON contains NO cleartext secrets
   (`password_hash` blanked, secret Setting rows dropped); `verify_password("",
   anything)` is False (no empty-hash bypass).
7. **test_certifications.py** — bulk renew of a cert issued Jan 31 with a
   1-month period → Feb 28/29, no ValueError; one bad cert doesn't abort the
   batch.
8. **test_incidents.py** — creating a grounding incident sets the vehicle to
   maintenance; **editing** an incident whose vehicle was manually returned to
   service does NOT re-ground it (transition guard).
9. **test_equipment.py** — battery merge repoints `battery_readings` +
   `equipment_checkouts`, writes an audit row, and rejects self-merge (400).
10. **test_geocode.py** — `/geocode` requires auth; mocked Nominatim: a result →
    `{lat,lon,display_name}`; empty → 404; upstream error → 502; a result with
    missing/bad lat/lon → 404 (not 500).
11. **test_schema.py** — `alembic upgrade head` on a fresh temp DB builds a
    schema whose tables/columns match `create_all`; `import app.main` succeeds;
    a re-run upgrade is a no-op.
12. **test_currency.py** — currency status math for a lapsed vs current pilot;
    the per-pilot `/needs-attention` endpoint returns the expected red/amber
    items.

(Pick the highest-value subset first if time-boxed: 1,2,3,4,5,6 are the
security/correctness core. 7–12 are important but second.)

Note: **CSP / nginx security headers are NOT testable via pytest** (they're set
in `nginx.conf`, outside the app). Verify those separately (see master plan W2);
do not add a pytest test for them.

## CI integration
Add a **separate** workflow `.github/workflows/tests.yml` running on `push` +
`pull_request`:
- checkout → set up Python 3.12 → `uv pip install` deps + `-r requirements.txt`
  (+ pytest, httpx) → `cd backend && PYTHONPATH=. pytest -q`.
- Pin actions to commit SHAs (match the repo convention in `docker-publish.yml`).
- Start **non-gating relative to the image build** (its own workflow), so a
  young/flaky suite never blocks a deploy. Once stable, optionally make
  `docker-publish` depend on tests (a `needs:` job or a single workflow) so a
  red test blocks publishing — decide with the user.

## Verification (of the suite itself)
- `cd backend && PYTHONPATH=. .venv/Scripts/python.exe -m pytest -q` passes
  locally.
- The `tests.yml` run is green in CI.
- Report coverage of the 12 areas (which are done) and any app bugs the tests
  surfaced (treat those as findings to fix or log).

## Out of scope (this pass)
- Frontend/Vitest tests (later phase).
- Load/perf tests.
- E2E/browser tests.
- Mutating the Docker image with test deps (tests run in CI/dev only).
