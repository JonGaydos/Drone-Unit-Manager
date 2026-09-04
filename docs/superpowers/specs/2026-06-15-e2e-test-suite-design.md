# E2E Test Suite (Playwright) — Design Spec

Date: 2026-06-15
Status: ready to plan. Self-contained. Third and final testing phase after the W1
backend pytest suite (71 tests, shipped) and the frontend Vitest suite (433 tests,
shipped). This adds browser-driven end-to-end tests with Playwright, exercising the
real backend + frontend together.

## Why

The unit (Vitest) suite mocks the network; nothing yet verifies the full stack
working together (real FastAPI + real React talking over HTTP, real auth, real DB
writes, real downloads). E2E covers critical user journeys plus a happy-path walk of
the feature areas, end to end, to catch integration regressions the mocked suites
cannot. Scope is comprehensive (user request): the critical journeys plus a
happy-path pass over the main feature areas.

## Environment / conventions

- App run model (decided): **dev servers**, not Docker. Backend `uvicorn app.main:app`
  on :8000; frontend Vite dev on :5173 (proxies `/api` -> :8000, per
  `frontend/vite.config.js`). Playwright drives `http://localhost:5173`.
- Tooling lives in `frontend/` (reuse its npm lockfile + Node). Playwright tests in
  `frontend/e2e/`; config `frontend/playwright.config.js`. **Chromium only** this
  phase.
- Backend bootstrap: app lifespan runs `alembic upgrade head` + `create_all` +
  `seed_defaults()` (only seeds after a user exists) + `init_install_token()`. A
  fresh empty `DATA_DIR` yields an empty DB; `settings.DATABASE_URL` /
  `TELEMETRY_DATABASE_URL` auto-derive from `DATA_DIR` when blank.
- First-run auth: `GET /api/auth/setup-required` -> `{setup_required}`;
  `POST /api/auth/setup` (open, no install token) creates the first admin from
  `{username, password, display_name, org_name, email?}`. Password rules: >=12 chars,
  >=1 uppercase, >=1 digit; username >=3 chars. Setup also creates a linked Pilot and
  seeds default folders + flight purposes. After setup, `POST /api/auth/login` ->
  `{token, user}`; the SPA stores `token`/`user` in localStorage and sends
  `Authorization: Bearer <token>`.
- Git discipline (CLAUDE.md): branch `tests/e2e-suite` off main, execute via
  subagent-driven development, merge `--ff-only`, push only when asked.

## Harness (build first)

### Dependencies
`@playwright/test` (devDependency in `frontend/`, npm). Browser binaries via
`npx playwright install chromium` (locally) / `--with-deps chromium` (CI).

### `frontend/playwright.config.js`
- `testDir: 'e2e'`, `fullyParallel: false`, `workers: 1` (one shared seeded DB this
  phase), `retries: process.env.CI ? 1 : 0`, `reporter: [['html'], ['list']]`.
- `use`: `baseURL: 'http://localhost:5173'`, `trace: 'on-first-retry'`,
  `screenshot: 'only-on-failure'`, `video: 'retain-on-failure'`,
  `storageState: 'e2e/.auth/admin.json'` (default authed state; specs override for
  anonymous or pilot-role).
- `globalSetup: './e2e/global-setup.js'`.
- `webServer`: an array of two:
  1. Backend: `command: 'node e2e/start-backend.mjs'`, `url:
     'http://localhost:8000/api/health'`, `reuseExistingServer: !process.env.CI`,
     `timeout: 120_000`.
  2. Frontend: `command: 'npm run dev'`, `url: 'http://localhost:5173'`,
     `reuseExistingServer: !process.env.CI`, `timeout: 120_000`.

### `frontend/e2e/start-backend.mjs` (cross-platform launcher)
- Computes a dedicated temp data dir (e.g. `frontend/e2e/.e2e-data`), **removes it**
  (fresh empty DB each run), recreates it.
- Resolves the Python interpreter: on Windows use
  `backend/.venv/Scripts/python.exe`; on CI/Linux use `python` (or the CI venv). This
  cross-platform path resolution is a known wrinkle the launcher must handle.
- Spawns `python -m uvicorn app.main:app --port 8000` with `cwd: backend/`, env
  `PYTHONPATH=.`, `DATA_DIR=<temp e2e data dir>`, `SECRET_KEY=e2e-secret-key`, and a
  fixed `TZ`. Pipes output; exits non-zero if uvicorn dies.

### `frontend/e2e/global-setup.js`
1. Launch a Chromium context, navigate to the app. If setup is required, **drive the
   setup wizard in the UI** (fill username/password/display name/org), submit, and
   assert it lands authenticated. This is the real setup-journey assertion.
2. Save the resulting authed state to `e2e/.auth/admin.json`.
3. Via authenticated API calls (`request` fixture with the admin token), seed baseline
   data the happy-path walks rely on: a few pilots, vehicles (+ a battery/controller/
   etc.), some flights, certification types + a cert, etc. Keep the seed small and
   deterministic; give seeded entities recognizable names.
4. Create a **pilot-role** user via API and save a second authed state to
   `e2e/.auth/pilot.json` for role-gating tests.

### `frontend/e2e/helpers/`
- `seed.js`: a thin authenticated API client (login, create pilot/vehicle/flight/...)
  used by global-setup and by specs that need their own fixtures.
- `selectors.js` / small page helpers: shared locators and navigation helpers, so
  specs read clearly and a UI change updates one place.

## Journeys (execution batches)

Each spec file is one batch dispatched to a fresh subagent. All run under the admin
`storageState` unless noted; mutating tests create **uniquely-named** entities (e.g.
`E2E Vehicle <Date.now()>`) and assert on their own rows, never on global counts.

1. `auth.spec.js` — login with seeded admin; logout returns to login; bad credentials
   show an inline error (no redirect loop); **role gating**: with `pilot.json` state,
   admin-only nav/actions (e.g. Audit Log, equipment edit/delete) are absent; with
   admin they are present. (Setup wizard itself is asserted in global-setup.)
2. `flights.spec.js` — log a flight via the UI (create -> appears in the flights list
   -> open its detail), apply a filter/search, perform a **bulk action** (select rows
   -> bulk update or delete) and confirm the list reflects it, and trigger a **CSV
   export** asserting a file download occurs.
3. `dashboard.spec.js` — dashboard loads with seeded data; key tiles render real
   values (no error state, no blank/`[object Object]`).
4. `fleet.spec.js` — add a vehicle through the UI, add a battery, open each detail
   page and confirm the entered data renders.
5. `pilots-compliance.spec.js` — add a pilot; view certifications; the compliance /
   currency view renders seeded red/amber/current items.
6. `incidents.spec.js` — create a **grounding** incident for an active vehicle via the
   UI; confirm end-to-end that the vehicle's status becomes maintenance (cross-cutting
   side effect across incidents + fleet).
7. `ops.spec.js` — happy-path create/view for mission logs, training logs, flight
   plans, and a checklist completion.
8. `misc.spec.js` — happy-path walks: Settings save persists; Integrations renders;
   Calendar, Documents, Media, Reports (generate), Analytics, Airspace, Weather each
   load and render their primary content end to end.

## CI integration

Add an `e2e` job to `.github/workflows/tests.yml` (sibling of the `pytest` and
`frontend` jobs; do not gate the image build):
- checkout (repo-pinned `actions/checkout` SHA) -> `actions/setup-node` (Node 22,
  npm cache) -> `actions/setup-python` (3.12) -> install backend deps with uv
  (`uv pip install --system -r backend/requirements.txt`) -> `npm ci` in `frontend/`
  -> `npx playwright install --with-deps chromium` -> `npm run e2e`.
- Upload the Playwright HTML report + traces as an artifact on failure
  (`actions/upload-artifact`, SHA-pinned). `reuseExistingServer:false` in CI so
  Playwright owns both servers.
- Pin every `uses:` to a 40-char commit SHA with a version comment (repo convention).
  Non-gating relative to docker-publish.

## Verification (of the suite itself)

- `cd frontend && npm run e2e` passes locally (Chromium), starting both servers from a
  fresh DB.
- The CI `e2e` job is green; report/trace artifacts upload on failure.
- Report which journeys are covered and any real app bugs the flows surfaced (log or
  fix, like the prior phases).

## Out of scope (this phase)

- Cross-browser (Firefox/WebKit) and mobile viewports.
- Visual-regression / screenshot-diff tests.
- Performance / load tests.
- The production/nginx/Docker path and CSP / security-header verification (we run dev
  servers; CSP remains a separate W2 follow-up).
- Production code changes beyond, if strictly necessary, adding a stable `data-testid`
  hook where no good user-visible/role selector exists.
