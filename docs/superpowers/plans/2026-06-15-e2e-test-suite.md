# E2E Test Suite (Playwright) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. Each Task is sized to one fresh subagent (isolated context) to bound token usage.

**Goal:** Build a Playwright E2E suite that drives the real backend + frontend together (Chromium, dev servers) across critical user journeys and a happy-path walk of the feature areas, wired into CI.

**Architecture:** Playwright `webServer` launches uvicorn (fresh temp DB via a cross-platform Node launcher) + Vite dev; `globalSetup` drives the setup wizard in-browser to create the admin (the setup-journey assertion), saves admin + pilot `storageState`, and seeds baseline data via authenticated API. Specs reuse `storageState`, assert on user-visible text/roles, and self-isolate mutating data with unique names. Task 0 builds the harness (gate); Tasks 1-8 add journey specs; Task 9 wires CI.

**Tech Stack:** Playwright (`@playwright/test`), Chromium, React 19 + Vite 8 frontend, FastAPI/uvicorn backend, npm.

**Spec:** `docs/superpowers/specs/2026-06-15-e2e-test-suite-design.md` (read it; this plan executes it).

**Working dir:** `frontend/`. Branch `tests/e2e-suite` (already created off main; do NOT switch). Commit after each task; no AI attribution.

---

## Shared contract (Tasks 1-8 rely on this; built in Task 0)

After Task 0, specs use:
- Default authed state: `playwright.config.js` sets `storageState: 'e2e/.auth/admin.json'`. A spec runs anonymously with `test.use({ storageState: { cookies: [], origins: [] } })`, or as pilot with `test.use({ storageState: 'e2e/.auth/pilot.json' })`.
- `e2e/helpers/seed.js` exports: `apiLogin(request, username, password) -> token`; `api(request, token)` -> a thin `{get, post, patch, del}` wrapper hitting `http://localhost:8000/api`; plus `createPilot/createVehicle/createFlight(...)` convenience creators returning the created entity. Specs needing their own fixtures call these (with the admin token from `e2e/.auth/admin.json` or by `apiLogin`).
- `e2e/helpers/app.js` exports small navigation/locator helpers (e.g. `gotoSection(page, 'Flights')`) so a nav change updates one place.
- Admin credentials (seeded in global-setup): username `e2eadmin`, password `E2eAdminPass1`. Pilot user: `e2epilot` / `E2ePilotPass1`.
- Backend base URL `http://localhost:8000`; app at `http://localhost:5173` (baseURL). API paths are under `/api`.
- Conventions: assert via Playwright locators on visible text/roles (`getByRole`, `getByText`, `getByLabel`); add a `data-testid` to a frontend component ONLY if no stable user-visible/role selector exists (note it in the report). Mutating specs name entities uniquely, e.g. `` `E2E Vehicle ${Date.now()}` `` , and assert on that row, never on global counts. Run a spec with `npm run e2e -- <file>`; run all with `npm run e2e`.

---

## Task 0: Harness (GATE — must land first)

**Files:**
- Modify: `frontend/package.json` (devDep + scripts)
- Modify: `frontend/.gitignore`
- Create: `frontend/playwright.config.js`
- Create: `frontend/e2e/start-backend.mjs`
- Create: `frontend/e2e/global-setup.js`
- Create: `frontend/e2e/helpers/seed.js`
- Create: `frontend/e2e/helpers/app.js`
- Create: `frontend/e2e/smoke.spec.js`

- [ ] **Step 1: Install Playwright + Chromium**

```bash
cd frontend
npm install -D @playwright/test
npx playwright install chromium
```

If npm reports a peer conflict with Vite 8, install the newest `@playwright/test` (it has no Vite peer dep, so none is expected). Do not use `--legacy-peer-deps` silently.

- [ ] **Step 2: Add scripts to `frontend/package.json`**

```json
"e2e": "playwright test",
"e2e:ui": "playwright test --ui",
"e2e:report": "playwright show-report"
```

- [ ] **Step 3: Ignore E2E artifacts — append to `frontend/.gitignore`**

```
# Playwright / E2E
/e2e/.auth
/e2e/.e2e-data
/test-results
/playwright-report
/blob-report
/playwright/.cache
```

- [ ] **Step 4: Create `frontend/e2e/start-backend.mjs`** (cross-platform: Windows venv, Linux venv, CI system python; wipes the temp DB each run)

```js
import { existsSync, rmSync, mkdirSync } from 'node:fs'
import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const here = path.dirname(fileURLToPath(import.meta.url))
const frontendDir = path.resolve(here, '..')
const repoRoot = path.resolve(frontendDir, '..')
const backendDir = path.join(repoRoot, 'backend')
const dataDir = path.join(here, '.e2e-data')

// Fresh empty DB every run.
if (existsSync(dataDir)) rmSync(dataDir, { recursive: true, force: true })
mkdirSync(dataDir, { recursive: true })

// Resolve a Python that has the backend deps (uvicorn, fastapi, ...).
const candidates = [
  path.join(backendDir, '.venv', 'Scripts', 'python.exe'), // Windows venv
  path.join(backendDir, '.venv', 'bin', 'python'),         // POSIX venv
]
const python = candidates.find(existsSync) || 'python' // CI: uv pip install --system

const proc = spawn(python, ['-m', 'uvicorn', 'app.main:app', '--port', '8000'], {
  cwd: backendDir,
  env: {
    ...process.env,
    PYTHONPATH: '.',
    DATA_DIR: dataDir,
    SECRET_KEY: 'e2e-secret-key-do-not-use-in-prod',
    TZ: 'America/Chicago',
  },
  stdio: 'inherit',
})
proc.on('exit', (code) => process.exit(code ?? 0))
process.on('SIGTERM', () => proc.kill('SIGTERM'))
process.on('SIGINT', () => proc.kill('SIGINT'))
```

VERIFY the backend venv actually has `uvicorn` (`backend/.venv/Scripts/python.exe -m uvicorn --version`). If not, install it into the venv (`uv pip install --python backend/.venv/Scripts/python.exe uvicorn`) and note it. Confirm `GET http://localhost:8000/api/health` returns 200 once running.

- [ ] **Step 5: Create `frontend/playwright.config.js`**

```js
import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: 'e2e',
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [['html', { open: 'never' }], ['list']],
  globalSetup: './e2e/global-setup.js',
  use: {
    baseURL: 'http://localhost:5173',
    storageState: 'e2e/.auth/admin.json',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: 'node e2e/start-backend.mjs',
      url: 'http://localhost:8000/api/health',
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command: 'npm run dev',
      url: 'http://localhost:5173',
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
})
```

- [ ] **Step 6: Create `frontend/e2e/helpers/seed.js`**

```js
const API = 'http://localhost:8000/api'

export async function apiLogin(request, username, password) {
  const res = await request.post(`${API}/auth/login`, { data: { username, password } })
  if (!res.ok()) throw new Error(`login failed: ${res.status()} ${await res.text()}`)
  return (await res.json()).token
}

export function api(request, token) {
  const headers = { Authorization: `Bearer ${token}` }
  return {
    get: (p) => request.get(`${API}${p}`, { headers }),
    post: (p, data) => request.post(`${API}${p}`, { headers, data }),
    patch: (p, data) => request.patch(`${API}${p}`, { headers, data }),
    del: (p) => request.delete(`${API}${p}`, { headers }),
  }
}

// Convenience creators (adjust required fields to the real schemas while implementing).
export async function createVehicle(request, token, fields) {
  const res = await api(request, token).post('/vehicles', fields)
  if (!res.ok()) throw new Error(`createVehicle: ${res.status()} ${await res.text()}`)
  return res.json()
}
export async function createPilotRecord(request, token, fields) {
  const res = await api(request, token).post('/pilots', fields)
  if (!res.ok()) throw new Error(`createPilot: ${res.status()} ${await res.text()}`)
  return res.json()
}
```

While implementing, read the real create schemas (the backend routers / the W1 backend tests) for required fields, and add the `createFlight`/`createCertType` helpers the seed needs.

- [ ] **Step 7: Create `frontend/e2e/global-setup.js`** (drives the setup wizard, saves admin + pilot states, seeds baseline)

```js
import { chromium, request as playwrightRequest } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import { apiLogin, api } from './helpers/seed.js'

const APP = 'http://localhost:5173'
const ADMIN = { username: 'e2eadmin', password: 'E2eAdminPass1', display: 'E2E Admin', org: 'E2E Unit' }
const PILOT = { username: 'e2epilot', password: 'E2ePilotPass1' }

export default async function globalSetup() {
  mkdirSync('e2e/.auth', { recursive: true })
  const browser = await chromium.launch()

  // 1) Setup wizard in the UI -> creates the first admin. This IS the setup journey.
  const page = await (await browser.newContext()).newPage()
  await page.goto(APP)
  // Read the real SetupPage to confirm field labels/roles; adjust the next lines to match.
  // The Vitest SetupPage.test.jsx encodes the real labels (username, password, display name, org).
  await page.getByLabel(/username/i).fill(ADMIN.username)
  await page.getByLabel(/password/i).first().fill(ADMIN.password)
  await page.getByLabel(/display name/i).fill(ADMIN.display)
  await page.getByLabel(/organization|org/i).fill(ADMIN.org)
  await page.getByRole('button', { name: /create|set ?up|continue|finish/i }).click()
  await page.waitForURL((u) => !/login|setup/.test(u.pathname), { timeout: 15_000 })
  await page.context().storageState({ path: 'e2e/.auth/admin.json' })
  await page.close()

  // 2) Seed baseline data + a pilot-role user via API (admin token).
  const reqCtx = await playwrightRequest.newContext()
  const adminToken = await apiLogin(reqCtx, ADMIN.username, ADMIN.password)
  const adminApi = api(reqCtx, adminToken)
  // Create a pilot-role login. Read the real user-create endpoint/payload (likely POST /auth/users
  // or /users with {username, password, role:'pilot'}). Adjust path/body to the real API.
  await adminApi.post('/auth/users', { username: PILOT.username, password: PILOT.password, role: 'pilot', display_name: 'E2E Pilot' })
  // Seed a few entities the happy-path walks rely on (vehicles, pilots, flights, cert types...).
  // Use the seed.js creators; keep it small + deterministic with recognizable names.

  // 3) Save a pilot storageState by logging in through the UI as the pilot.
  const pilotPage = await (await browser.newContext()).newPage()
  await pilotPage.goto(`${APP}/login`)
  await pilotPage.getByLabel(/username/i).fill(PILOT.username)
  await pilotPage.getByLabel(/password/i).fill(PILOT.password)
  await pilotPage.getByRole('button', { name: /sign in|log ?in/i }).click()
  await pilotPage.waitForURL((u) => !/login/.test(u.pathname), { timeout: 15_000 })
  await pilotPage.context().storageState({ path: 'e2e/.auth/pilot.json' })
  await pilotPage.close()

  await reqCtx.dispose()
  await browser.close()
}
```

VERIFY against real UI/API while implementing: the SetupPage field labels + submit button text (cross-check `frontend/src/pages/SetupPage.test.jsx`), the LoginPage labels/button (`LoginPage.test.jsx`), and the real user-create endpoint + payload (read the backend `auth`/`users` router). Fix selectors/paths to match. If setup is multi-step, complete each step. If the wizard offers an optional second step, skip/finish it so it lands authenticated.

- [ ] **Step 8: Create `frontend/e2e/helpers/app.js`**

```js
import { expect } from '@playwright/test'

// Navigate via the sidebar by visible link name; adjust if the nav uses different labels.
export async function gotoSection(page, name) {
  await page.getByRole('link', { name }).click()
  await expect(page).toHaveURL(new RegExp(name.toLowerCase().replace(/\s+/g, '-')))
}
```

Adjust to the real Sidebar link names/routes while implementing (the Vitest `Sidebar.test.jsx` encodes them).

- [ ] **Step 9: Create `frontend/e2e/smoke.spec.js`**

```js
import { test, expect } from '@playwright/test'

test('app loads authenticated and shows the dashboard', async ({ page }) => {
  await page.goto('/')
  // Adjust the assertion to a real stable element on the landing page.
  await expect(page.getByRole('heading', { name: /dashboard/i })).toBeVisible({ timeout: 15_000 })
})
```

- [ ] **Step 10: Run the smoke test (boots both servers from a fresh DB, runs global-setup)**

Run: `cd frontend && npm run e2e -- smoke.spec.js`
Expected: global-setup completes (admin created via the wizard, states saved), then 1 passed. Iterate until green: fix selectors against the real SetupPage/LoginPage/Dashboard, confirm the backend launcher + health gate work, confirm `.auth/admin.json` is written. This gate must be solid.

- [ ] **Step 11: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/.gitignore frontend/playwright.config.js frontend/e2e
git commit -m "test(e2e): playwright harness (dev-server webServer, setup-wizard global-setup, seed helpers, smoke)"
```

---

## Journey specs — shared instructions for Tasks 1-8

For each spec: read the relevant page sources + their Vitest tests (which encode real labels/roles/endpoints) FIRST. Use the admin `storageState` by default; override per the contract for anonymous/pilot. Drive the real UI with Playwright locators and assert on visible results; where a flow needs preexisting data, seed it via `e2e/helpers/seed.js` with uniquely-named entities. A real app bug a flow surfaces (a journey that breaks end to end) → report as a FINDING; do not work around it. Run `npm run e2e -- <file>` then the whole suite `npm run e2e` before committing.

## Task 1: `e2e/auth.spec.js`
- [ ] Login: anonymous state (`test.use({ storageState: { cookies: [], origins: [] } })`) → visit `/login`, sign in as `e2eadmin`/`E2eAdminPass1`, assert it lands on an authed page (dashboard/nav visible).
- [ ] Logout returns to `/login` (or shows the login form).
- [ ] Bad credentials show an inline error and stay on login (no redirect loop).
- [ ] Role gating: with `e2e/.auth/pilot.json`, an admin-only nav/action (e.g. Audit Log link, or an equipment Edit/Delete) is ABSENT; with admin it is PRESENT. (Read `Sidebar.jsx` for the real admin-only item.)
- [ ] Commit `test(e2e): auth + role gating journey`.

## Task 2: `e2e/flights.spec.js`
- [ ] Log a flight via the UI: open the create form, fill required fields (read FlightsPage / the create modal for the real fields; pick a seeded pilot+vehicle), submit, assert the new flight appears in the list, open its detail and confirm a field rendered.
- [ ] Filter/search narrows the list to the created flight.
- [ ] Bulk action: select the created row(s), run a bulk update or delete, assert the list reflects it.
- [ ] CSV export: trigger the export and assert a download occurs (`page.waitForEvent('download')`), filename non-empty.
- [ ] Commit `test(e2e): flights log/filter/bulk/export journey`.

## Task 3: `e2e/dashboard.spec.js`
- [ ] Dashboard loads with seeded data: key tiles render real values; no error banner; assert `[object Object]` is absent from the page.
- [ ] Commit `test(e2e): dashboard loads with seeded data`.

## Task 4: `e2e/fleet.spec.js`
- [ ] Add a vehicle via the UI (unique serial/name), assert it appears in the fleet list and its detail page shows the entered data.
- [ ] Add a battery (unique), assert it renders.
- [ ] Commit `test(e2e): fleet add vehicle + battery journey`.

## Task 5: `e2e/pilots-compliance.spec.js`
- [ ] Add a pilot via the UI (unique name), assert it appears in the pilots list / detail.
- [ ] Certifications view renders; the compliance/currency view shows seeded status items (red/amber/current) end to end.
- [ ] Commit `test(e2e): pilots + compliance journey`.

## Task 6: `e2e/incidents.spec.js`
- [ ] Seed an active vehicle (unique). Create a GROUNDING incident for it via the UI (set the grounding flag/field). Assert end-to-end that the vehicle's status becomes maintenance (check the vehicle in the fleet UI or its detail page). This is the cross-cutting side-effect journey.
- [ ] Commit `test(e2e): incident grounding -> vehicle maintenance journey`.

## Task 7: `e2e/ops.spec.js`
- [ ] Happy-path create + view for a mission log, a training log, a flight plan, and a checklist completion (each with unique data; read each page for real fields). Assert each created item renders.
- [ ] Commit `test(e2e): ops (mission/training/flight-plans/checklist) journeys`.

## Task 8: `e2e/misc.spec.js`
- [ ] Settings: change a non-secret setting and save; reload and assert it persisted.
- [ ] Walk each remaining area end to end, asserting primary content renders without error: Integrations, Calendar, Documents, Media, Reports (generate a report), Analytics, Airspace, Weather.
- [ ] Commit `test(e2e): settings save + feature-area happy-path walks`.

---

## Task 9: CI — add `e2e` job to tests.yml

**Files:** Modify `.github/workflows/tests.yml`.

- [ ] **Step 1: Read** `.github/workflows/tests.yml` (has `pytest` + `frontend` jobs) and `docker-publish.yml` (SHA-pin convention).
- [ ] **Step 2: Add an `e2e` job** (sibling; do not change existing jobs):

```yaml
  e2e:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@<repo's checkout SHA>  # vX.Y.Z
      - name: Set up Python 3.12
        uses: actions/setup-python@<repo's setup-python SHA>  # vX.Y.Z
        with:
          python-version: '3.12'
      - name: Set up uv
        uses: astral-sh/setup-uv@<repo's setup-uv SHA>  # vX.Y.Z
      - name: Install backend deps
        run: uv pip install --system -r backend/requirements.txt
      - name: Set up Node
        uses: actions/setup-node@<repo's setup-node SHA>  # vX.Y.Z
        with:
          node-version: '22'
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - name: Install frontend deps
        working-directory: frontend
        run: npm ci
      - name: Install Playwright Chromium
        working-directory: frontend
        run: npx playwright install --with-deps chromium
      - name: Run E2E
        working-directory: frontend
        run: npm run e2e
      - name: Upload Playwright report
        if: failure()
        uses: actions/upload-artifact@<pinned SHA>  # vX.Y.Z
        with:
          name: playwright-report
          path: frontend/playwright-report
          retention-days: 7
```

Reuse the EXACT checkout/setup-python/setup-uv/setup-node SHAs already pinned in the repo's workflows; pin `actions/upload-artifact` to a real published v4 SHA (verify via the GitHub API) with a version comment. In CI `reuseExistingServer` is false (the config already keys off `process.env.CI`), so Playwright owns both servers. Non-gating (its own job; no `needs:` from docker-publish).
- [ ] **Step 3:** Validate the YAML parses; confirm every `uses:` is a 40-char SHA + version comment.
- [ ] **Step 4: Commit** `ci: add e2e (playwright) job to tests workflow`.

---

## Final

After Task 9: run `cd frontend && npm run e2e` (whole suite green from a fresh DB), then use **superpowers:finishing-a-development-branch** (verify → ff-only merge to main → push only when asked). Report journeys covered, any app findings, and any `data-testid` hooks added to source.

## Self-Review (completed by plan author)

- **Spec coverage:** Task 0 = harness (config, launcher, global-setup, seed/app helpers, smoke) covering the spec's Harness section incl. setup-wizard-in-globalSetup, admin+pilot storageState, API seeding; Tasks 1-8 = the 8 journey spec files (auth/role-gating, flights+export, dashboard, fleet, pilots/compliance, incident-grounding, ops, misc walk) — one per spec batch; Task 9 = CI e2e job with report artifact. All spec sections mapped.
- **Placeholders:** Task 0 ships concrete code; journey tasks are behavior-specified (deliverable is browser flows discovered from the real UI, like the prior two plans) — intentional, not a gap. Selectors in Task 0's sample code are explicitly flagged to verify against the real SetupPage/LoginPage/Sidebar (and their Vitest tests).
- **Naming consistency:** `apiLogin`/`api`/`createVehicle`/`createPilotRecord` (seed.js), `gotoSection` (app.js), `e2e/.auth/admin.json` + `e2e/.auth/pilot.json`, admin `e2eadmin`/`E2eAdminPass1`, pilot `e2epilot`/`E2ePilotPass1` used consistently across tasks.
- **Known risks surfaced:** cross-platform python resolution + uvicorn-in-venv (Task 0 Step 4); real setup/login/user-create selectors+endpoints to verify (Task 0 Step 7); `workers:1` shared-DB isolation handled by unique-data discipline (shared contract).
