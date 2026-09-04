# Frontend Test Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Each Task is sized to one fresh subagent (isolated context) to bound token usage.

**Goal:** Build an exhaustive Vitest + React Testing Library + MSW frontend test suite for Drone Unit Manager, covering lib utilities, the API client, contexts, hooks, all components, and all 37 pages, wired into CI.

**Architecture:** MSW intercepts `fetch` at the network boundary so the real `@/api/client` runs inside tests; a shared `renderWithProviders` helper wraps router + Auth/Theme/Toast; jsdom-incompatible libs (leaflet/fullcalendar/recharts) are stubbed at module level. Tests assert behavior via roles/text, not DOM snapshots. Task 0 builds the harness (the gate); Tasks 1-10 add tests by area; Task 11 wires CI.

**Tech Stack:** React 19, Vite 8, Tailwind 4, react-router 7, Vitest, @testing-library/react, @testing-library/user-event, @testing-library/jest-dom, jsdom, msw (all npm).

**Spec:** `docs/superpowers/specs/2026-06-15-frontend-test-suite-design.md` (read it; this plan executes it).

**Working dir:** `frontend/`. Branch `tests/frontend-suite` (already created off main; do NOT switch). Commit after each task; no AI attribution.

---

## Shared harness contract (Tasks 1-10 rely on this; built in Task 0)

Once Task 0 lands, every later task uses these from `@/test/*` (alias `@` → `frontend/src`):

- `renderWithProviders(ui, { route = '/', user, role })` from `src/test/render.jsx` — renders `ui` inside `MemoryRouter` + `AuthProvider` + `ThemeProvider` + `ToastProvider`. When `user` (an object) or `role` (a string) is passed, seeds `localStorage` `token`="test-token" + `user` so `AuthProvider`'s `/auth/me` mount path resolves to that user. Returns the RTL render result plus `user` (a `userEvent` instance). For routed/detail pages, pass `route` like `/pilots/1` and render the app's `<Routes>` subtree or the page with a `MemoryRouter` + `Routes` wrapper exposing the `:id` param (helper `renderRoute`).
- `server` from `src/test/server.js` — the MSW `setupServer` instance. Override per test: `server.use(http.get('/api/...', () => HttpResponse.json(...)))`. Default handlers live in `src/test/handlers.js`.
- MSW request helpers: import `http, HttpResponse` from `msw`.
- jsdom polyfills + leaflet/fullcalendar/recharts module stubs are registered globally in `src/test/setup.js` — no per-test setup needed for those.

Conventions:
- Test files are colocated: `Foo.test.jsx` next to `Foo.jsx`; lib tests `foo.test.js` next to `foo.js`.
- Assert via Testing Library queries (`getByRole`, `getByText`, `findBy*` for async). No DOM snapshots.
- For a page's "error state" test, override the page's primary endpoint with `HttpResponse.json({detail:'boom'}, {status:500})` and assert an error UI appears (not a blank render / unhandled throw).
- Real app bugs found (page crashes on a valid payload, missing empty/error state, object rendered raw into JSX) are reported as FINDINGS, not masked by weakening the test.
- Run a task's tests with `npm run test:run -- <path>`; run the whole suite with `npm run test:run` before committing.

---

## Task 0: Foundation (harness) — GATE, must land first

**Files:**
- Modify: `frontend/package.json` (devDependencies + scripts)
- Modify: `frontend/vite.config.js` (add `test` block)
- Create: `frontend/src/test/setup.js`
- Create: `frontend/src/test/server.js`
- Create: `frontend/src/test/handlers.js`
- Create: `frontend/src/test/render.jsx`
- Create: `frontend/src/test/smoke.test.jsx`

- [ ] **Step 1: Install test dependencies (npm, compatible with Vite 8)**

```bash
cd frontend
npm install -D vitest @vitest/coverage-v8 jsdom @testing-library/react @testing-library/user-event @testing-library/jest-dom msw
```

KNOWN RISK: the project uses Vite 8 (bleeding edge). If npm reports a peer-dependency conflict between `vitest` and `vite@8`, resolve it (install the newest `vitest` that supports Vite 8; check `npm view vitest peerDependencies`). Do NOT downgrade Vite. If no compatible Vitest release supports Vite 8 yet, STOP and report as BLOCKED with the peer ranges — do not force with `--legacy-peer-deps` silently.

- [ ] **Step 2: Add scripts to `frontend/package.json`**

In the `"scripts"` block add:

```json
"test": "vitest",
"test:run": "vitest run",
"test:coverage": "vitest run --coverage"
```

- [ ] **Step 3: Add the `test` block to `frontend/vite.config.js`**

Add a `test` key to the `defineConfig({...})` object (keep all existing plugins/resolve/build/server):

```js
test: {
  environment: 'jsdom',
  globals: true,
  setupFiles: ['./src/test/setup.js'],
  css: true,
  coverage: {
    provider: 'v8',
    exclude: ['src/test/**', 'src/main.jsx', '**/*.config.js', 'dist/**'],
  },
},
```

If Vitest complains that the Vite config import of `@tailwindcss/vite` breaks jsdom test runs, gate the tailwind plugin out under test via `process.env.VITEST` (only if needed) and note it.

- [ ] **Step 4: Create `frontend/src/test/server.js`**

```js
import { setupServer } from 'msw/node'
import { handlers } from './handlers'

export const server = setupServer(...handlers)
```

- [ ] **Step 5: Create `frontend/src/test/handlers.js`**

```js
import { http, HttpResponse } from 'msw'

// Minimal defaults so AuthProvider's mount validation resolves for an
// authenticated render. Tests override per-case with server.use(...).
export const handlers = [
  http.get('/api/auth/me', () =>
    HttpResponse.json({ id: 1, username: 'admin', role: 'admin' })),
]
```

- [ ] **Step 6: Create `frontend/src/test/setup.js`**

```js
import '@testing-library/jest-dom/vitest'
import { afterAll, afterEach, beforeAll, vi } from 'vitest'
import { cleanup } from '@testing-library/react'
import { server } from './server'

// --- jsdom gaps ---
globalThis.matchMedia ||= (query) => ({
  matches: false, media: query, onchange: null,
  addListener() {}, removeListener() {},
  addEventListener() {}, removeEventListener() {}, dispatchEvent() { return false },
})
class _Observer { observe() {} unobserve() {} disconnect() {} takeRecords() { return [] } }
globalThis.ResizeObserver ||= _Observer
globalThis.IntersectionObserver ||= _Observer
globalThis.URL.createObjectURL ||= () => 'blob:mock'
globalThis.URL.revokeObjectURL ||= () => {}
Element.prototype.scrollTo ||= () => {}

// --- module stubs for jsdom-incompatible libs ---
vi.mock('react-leaflet', () => {
  const Stub = ({ children }) => <div data-testid="leaflet-stub">{children}</div>
  return {
    MapContainer: Stub, TileLayer: () => null, Marker: Stub, Popup: Stub,
    Circle: () => null, Polyline: () => null, useMap: () => ({}), useMapEvents: () => ({}),
  }
})
vi.mock('leaflet', () => ({ default: { icon: () => ({}), divIcon: () => ({}), Icon: { Default: { mergeOptions() {}, prototype: {} } } } }))
vi.mock('@fullcalendar/react', () => ({ default: () => <div data-testid="fullcalendar-stub" /> }))
vi.mock('@fullcalendar/daygrid', () => ({ default: {} }))
vi.mock('@fullcalendar/timegrid', () => ({ default: {} }))
vi.mock('@fullcalendar/list', () => ({ default: {} }))
vi.mock('@fullcalendar/interaction', () => ({ default: {} }))
vi.mock('recharts', async (orig) => {
  // Render children in a sized container so charts mount in jsdom.
  const actual = await orig()
  return { ...actual, ResponsiveContainer: ({ children }) => <div data-testid="recharts-stub" style={{ width: 800, height: 400 }}>{children}</div> }
})

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => { server.resetHandlers(); cleanup(); localStorage.clear() })
afterAll(() => server.close())
```

NOTE: confirm the real import surface of `react-leaflet`/`leaflet`/`@fullcalendar/*`/`recharts` actually used by `FlightMap.jsx`, `AirspacePage.jsx`, `CalendarPage.jsx`, `AnalyticsPage.jsx`, `DashboardPage.jsx`. Add any missing named exports to the stubs so those modules import cleanly. Keep stubs minimal.

- [ ] **Step 7: Create `frontend/src/test/render.jsx`**

```jsx
import { render } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { AuthProvider } from '@/contexts/AuthContext'
import { ThemeProvider } from '@/contexts/ThemeContext'
import { ToastProvider } from '@/contexts/ToastContext'

// Read the real provider export names from each context file; adjust the
// imports above if a provider is named/exported differently.

function Providers({ children }) {
  return (
    <ThemeProvider>
      <ToastProvider>
        <AuthProvider>{children}</AuthProvider>
      </ToastProvider>
    </ThemeProvider>
  )
}

export function renderWithProviders(ui, { route = '/', user, role } = {}) {
  if (user || role) {
    localStorage.setItem('token', 'test-token')
    localStorage.setItem('user', JSON.stringify(user || { id: 1, username: 'admin', role: role || 'admin' }))
  }
  const result = render(
    <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>,
    { wrapper: Providers },
  )
  return { user: userEvent.setup(), ...result }
}

// For pages that read route params, e.g. /pilots/:id
export function renderRoute(element, { path, route, user, role } = {}) {
  if (user || role) {
    localStorage.setItem('token', 'test-token')
    localStorage.setItem('user', JSON.stringify(user || { id: 1, username: 'admin', role: role || 'admin' }))
  }
  return {
    user: userEvent.setup(),
    ...render(
      <MemoryRouter initialEntries={[route]}>
        <Routes><Route path={path} element={element} /></Routes>
      </MemoryRouter>,
      { wrapper: Providers },
    ),
  }
}
```

VERIFY: open `src/contexts/AuthContext.jsx`, `ThemeContext.jsx`, `ToastContext.jsx` and confirm the provider export names (`AuthProvider` is confirmed; check Theme/Toast). Fix imports to match. If a provider requires props, supply sane defaults.

- [ ] **Step 8: Create the smoke test `frontend/src/test/smoke.test.jsx`**

```jsx
import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'

describe('harness', () => {
  it('renders a component through the providers', () => {
    renderWithProviders(<div>hello harness</div>)
    expect(screen.getByText('hello harness')).toBeInTheDocument()
  })

  it('MSW intercepts an api call', async () => {
    server.use(http.get('/api/ping', () => HttpResponse.json({ ok: true })))
    const { api } = await import('@/api/client')
    await expect(api.get('/ping')).resolves.toEqual({ ok: true })
  })
})
```

- [ ] **Step 9: Run the smoke test**

Run: `npm run test:run -- src/test/smoke.test.jsx`
Expected: 2 passed. If MSW reports an unhandled request or the providers throw, fix the harness until green. This gate must be solid — every later task inherits it.

- [ ] **Step 10: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vite.config.js frontend/src/test
git commit -m "test(frontend): vitest + RTL + MSW harness (config, providers, mocks, smoke)"
```

---

## Task 1: lib/ unit tests

**Files:** Create `src/lib/formatters.test.js`, `src/lib/utils.test.js`, `src/lib/location.test.js`, `src/lib/a11y.test.js`, `src/lib/constants.test.js`. Read each source file first for exact signatures/behavior.

- [ ] **Step 1: Read sources** — `src/lib/{formatters,utils,location,a11y,constants}.js`.
- [ ] **Step 2: Write tests** asserting:
  - `formatters`: `formatDuration`/`formatHours` (zero, null/undefined, large values), `metersToFeet`/`mpsToMph` (known conversions + zero/negative/null), `formatDate`/`formatDateTime` (valid ISO, null/empty → graceful, invalid string), `daysUntil` (past=negative, today=0, future=positive), `normalizeDateValue` (its documented input/output forms). Assert exact outputs.
  - `utils`: `cn` (merges + later class wins per tailwind-merge), `sortByName`/`sortByField`/`sortPilots`/`sortVehicles`/`sortPilotsActiveFirst` (ordering + stability + active-first), `vehicleDisplayName`/`equipmentDisplayName` (full data + missing fields fallback), `formatStatusText` (snake/kebab → human).
  - `location`: `resolveOrgLocation` (settings present → those coords; absent/partial → `DEFAULT_ORG_LOCATION`).
  - `a11y`: `interactiveProps` (returns role/tabIndex/keyboard handler shape; Enter/Space triggers the handler).
  - `constants`: each exported color map is a non-empty object with expected status keys (light shape assertion).
- [ ] **Step 3: Run** `npm run test:run -- src/lib` → all pass. Fix or log findings.
- [ ] **Step 4: Run full suite** `npm run test:run` → green.
- [ ] **Step 5: Commit** `test(frontend): lib unit tests (formatters, utils, location, a11y, constants)`

---

## Task 2: api/client tests

**Files:** Create `src/api/client.test.js`. Read `src/api/client.js` first.

- [ ] **Step 1: Write tests** (MSW-backed; import `{ api, resetSessionExpired }` from `@/api/client`):
  - get/post/patch/put/delete hit the right method+path and return parsed JSON (assert via MSW handler capturing method/body).
  - 401 → throws "Session expired...", clears `localStorage` token+user, sets `globalThis.location.href` to `/login` exactly once across two concurrent 401s; after `resetSessionExpired()` a new 401 redirects again. (Stub `globalThis.location` with a writable `href`.)
  - timeout → with `{ timeout: 1 }` against a delayed handler, throws "The request timed out. Please try again."; `{ timeout: 0 }` disables it.
  - 204 → `null`; 200 empty body → `null`.
  - error sanitization: string `detail` passthrough; array `detail` joined with `; `; a `detail` containing `SQL`/`Traceback`/`/app/` → generic "unexpected error" message.
  - `download`/`downloadPost`: `Content-Disposition` filename parsing — RFC 5987 `filename*=UTF-8''a%20b.csv` → `a b.csv`; legacy `filename="x.csv"` → `x.csv`; absent → fallback (`export.csv`/`report.pdf`). (Stub anchor click + `URL.createObjectURL`.)
  - `upload`: non-OK with array detail → joined message; SQL/Traceback/path → generic.
- [ ] **Step 2: Run** `npm run test:run -- src/api` → pass. **Step 3:** full suite green. **Step 4: Commit** `test(frontend): api client (401/timeout/204/sanitization/filename/upload)`

---

## Task 3: contexts + hooks tests

**Files:** Create `src/contexts/AuthContext.test.jsx`, `ThemeContext.test.jsx`, `ToastContext.test.jsx`, `src/hooks/useConfirm.test.jsx`, `src/hooks/useViewTransition.test.js`. Read each source first.

- [ ] **Step 1: Write tests:**
  - `AuthContext`: a test consumer using `useAuth`. `login()` posts `/auth/login` (MSW), stores token, sets user; `logout()` clears storage + user; `updateUser` merges; role booleans correct for each role value (admin, supervisor, pilot, manager, viewer); on mount with a stored token, `/auth/me` success sets user, failure clears token; `useAuth` outside provider throws.
  - `ThemeContext`: default theme, toggle flips + persists to localStorage, respects `matchMedia` system preference (override the matchMedia mock).
  - `ToastContext`: add shows a toast, remove hides it, auto-dismiss after timeout (use `vi.useFakeTimers()`).
  - `useConfirm`: returns a confirm fn + dialog state; resolving true on confirm, false/reject on cancel.
  - `useViewTransition`: calls `document.startViewTransition` when present; falls back to running the callback directly when absent.
- [ ] **Step 2-4:** run scoped, then full suite, commit `test(frontend): contexts (auth/theme/toast) + hooks`

---

## Task 4: ui components tests

**Files:** Create `*.test.jsx` next to each in `src/components/ui/`: Button, Modal, ConfirmDialog, DataTable, Input, Select, Badge, StatCard, Card, PageErrorBoundary. Read each source first.

- [ ] **Step 1: Write tests** (use `renderWithProviders` if a component reads context; otherwise plain `render`):
  - Button: renders label, fires `onClick`, respects `disabled`, applies variant classes.
  - Modal: hidden when closed; open shows content; closes via close button, Escape key, and overlay click (whichever the component supports — assert the ones it implements).
  - ConfirmDialog: confirm button fires confirm callback, cancel fires cancel.
  - DataTable: renders given rows/columns, sort control toggles order, empty data shows empty state.
  - Input/Select: render with label, fire `onChange` with `user.type`/`user.selectOptions`, associate label↔control (a11y).
  - Badge/StatCard: render by status/value props (correct text + status class).
  - Card: renders children/header.
  - PageErrorBoundary: a child that throws renders the fallback UI (not a blank screen). Suppress the expected console.error in this test.
- [ ] **Step 2-4:** scoped run, full suite, commit `test(frontend): ui components`

---

## Task 5: layout + feature components tests

**Files:** Create `*.test.jsx` for `src/components/layout/{Layout,Sidebar,TopBar}.jsx` and `src/components/{CommandPalette,FlightMap,LinkedPhotos,ImportMappingModal,DocumentUpload}.jsx`. Read each source first.

- [ ] **Step 1: Write tests** (render with `renderWithProviders`, seed `role` to exercise gating):
  - Layout: renders navigation + the child route content (outlet).
  - Sidebar: as `role: 'admin'` shows admin-only links; as `role: 'pilot'` and `role: 'viewer'` those admin links are absent; active route is highlighted.
  - TopBar: shows search / command-palette trigger; user menu logout calls AuthContext.logout (assert redirect/user cleared).
  - CommandPalette: opens on Ctrl+K (`user.keyboard('{Control>}k{/Control}')`), filters as you type, selecting a result navigates (assert via a route-probe or mocked navigate).
  - FlightMap: renders with the leaflet stub; with no/invalid coordinates renders gracefully (no throw).
  - LinkedPhotos: lists linked photos from a mocked endpoint; link/unlink actions call the API (assert via MSW handler hit).
  - ImportMappingModal: renders the column-mapping UI from a given schema; submitting maps columns and calls the provided callback/endpoint.
  - DocumentUpload: selecting a file then submitting calls `api.upload` (MSW); error response surfaces a message.
- [ ] **Step 2-4:** scoped run, full suite, commit `test(frontend): layout + feature components`

---

## Pages — shared instructions for Tasks 6-10

For EACH page in the batch:
1. Read the page source to learn its endpoints, route, and key UI.
2. Add `<PageName>.test.jsx` next to it. Use `renderWithProviders` (seed `role: 'admin'` unless the page is role-specific). For detail pages use `renderRoute` with the real route + a mocked entity, and add MSW handlers for every endpoint the page calls on mount.
3. Cover the **baseline**: (a) renders without crashing; (b) loading → data (mock a populated payload, assert real content appears via `findBy*`); (c) empty state (mock empty list/payload, assert the empty UI); (d) **error state — override the primary endpoint with a 500 and assert an error UI appears, not a blank render or unhandled throw.**
4. Add the **richer interaction tests** noted for specific pages below.
5. A real bug (crash on valid payload, missing empty/error handling, object rendered raw) → report as a FINDING; do not weaken the test.
Run `npm run test:run -- <batch paths>` then the full suite; commit per batch.

## Task 6: pages — auth/dashboard/home

**Files (create `*.test.jsx` next to each):** `pages/LoginPage`, `pages/SetupPage`, `pages/DashboardPage`, `pages/FleetHealthPage`, `pages/NotFoundPage`, `pages/UserManualPage`, `pages/AuditLogPage`.
- [ ] Baseline for all 7 (NotFoundPage/UserManualPage may be static — at minimum assert they render expected content; skip empty/error if they make no API calls, and note that).
- [ ] **LoginPage** interaction: typing creds + submit calls `/auth/login` (MSW) and on success navigates away; a 401 shows an inline error (not a redirect loop).
- [ ] **DashboardPage** React #31 regression: mock a fully-populated dashboard payload INCLUDING object-valued fields (e.g. a `weather`/`station` object); assert the page renders text and does NOT throw / does not render `[object Object]`. This is the headline regression test.
- [ ] Run scoped + full suite; commit `test(frontend): pages — auth/dashboard/home`

## Task 7: pages — fleet/equipment

**Files:** `pages/FleetPage`, `pages/VehicleDetailPage`, `pages/BatteryDetailPage`, `pages/ControllerDetailPage`, `pages/DockDetailPage`, `pages/SensorDetailPage`, `pages/AttachmentDetailPage`, `pages/MaintenancePage`.
- [ ] Baseline for all 8 (detail pages via `renderRoute` with a route param + mocked entity).
- [ ] FleetPage interaction: a primary filter or row navigation works.
- [ ] Run scoped + full suite; commit `test(frontend): pages — fleet/equipment`

## Task 8: pages — flights/ops

**Files:** `pages/FlightsPage`, `pages/FlightDetailPage`, `pages/FlightPlansPage`, `pages/IncidentPage`, `pages/MissionLogPage`, `pages/TrainingLogPage`, `pages/ChecklistPage`.
- [ ] Baseline for all 7.
- [ ] **FlightsPage** interaction: filtering narrows the list; selecting rows + a bulk action (delete/update) calls the bulk endpoint (MSW handler hit asserted).
- [ ] **IncidentPage** interaction: create/edit primary flow submits to the API.
- [ ] Run scoped + full suite; commit `test(frontend): pages — flights/ops`

## Task 9: pages — pilots/compliance

**Files:** `pages/PilotsPage`, `pages/PilotDetailPage`, `pages/CertificationsPage`, `pages/CompliancePage`, `pages/CheckoutsPage`, `pages/AlertsPage`.
- [ ] Baseline for all 6.
- [ ] **PilotsPage** interaction: primary create/edit flow submits to the API.
- [ ] Run scoped + full suite; commit `test(frontend): pages — pilots/compliance`

## Task 10: pages — settings/misc

**Files:** `pages/SettingsPage`, `pages/IntegrationsPage`, `pages/AnalyticsPage`, `pages/CalendarPage`, `pages/AirspacePage`, `pages/WeatherPage`, `pages/MediaPage`, `pages/DocumentStoragePage`, `pages/ReportsPage`.
- [ ] Baseline for all 9 (AnalyticsPage uses recharts stub; CalendarPage uses fullcalendar stub; AirspacePage uses leaflet stub — verify they render under the stubs).
- [ ] **SettingsPage** interaction: secret fields render redacted (`********`); a save submits to the API.
- [ ] Run scoped + full suite; commit `test(frontend): pages — settings/misc`

---

## Task 11: CI — add frontend job to tests.yml

**Files:** Modify `.github/workflows/tests.yml`.

- [ ] **Step 1: Read** the current `.github/workflows/tests.yml` and `.github/workflows/docker-publish.yml` (for SHA-pin convention).
- [ ] **Step 2: Add a second job** `frontend` alongside the existing `pytest` job (do not change the backend job):

```yaml
  frontend:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@<same SHA as docker-publish.yml>  # vX.Y.Z
      - name: Set up Node
        uses: actions/setup-node@<pinned SHA>  # vX.Y.Z
        with:
          node-version: '22'
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - name: Install dependencies
        working-directory: frontend
        run: npm ci
      - name: Run frontend tests
        working-directory: frontend
        run: npm run test:run
```

Pin `actions/setup-node` to a real published 40-char commit SHA (verify via the GitHub API like the backend workflow did) with a trailing version comment. Reuse the exact `actions/checkout` SHA already in the repo. Non-gating (its own job; does not block docker-publish).
- [ ] **Step 3:** Validate YAML parses; confirm `npm run test:run` passes locally one more time.
- [ ] **Step 4: Commit** `ci: add frontend vitest job to tests workflow`

---

## Final

After Task 11: run `cd frontend && npm run test:run` (whole suite green), then use **superpowers:finishing-a-development-branch** (verify tests → ff-only merge to main → push only when asked). Report total test count, coverage by area, and any app findings surfaced.

## Self-Review (completed by plan author)

- **Spec coverage:** Task 0 = infra; Task 1 = lib; Task 2 = api/client; Task 3 = contexts+hooks; Task 4 = ui; Task 5 = layout+feature; Tasks 6-10 = all 37 pages (7+8+7+6+9, each page once, matches spec batches incl. ChecklistPage); Task 11 = CI. All spec sections mapped.
- **Placeholders:** Batch 0 has concrete code; test batches are behavior-specified (deliverable is tests discovered from source, like the W1 backend plan) — intentional, not a placeholder gap.
- **Naming consistency:** `renderWithProviders`/`renderRoute`/`server`/`@/test/*` used consistently across tasks; provider/import names flagged for verification against source in Task 0.
- **Known risk surfaced:** Vitest↔Vite 8 peer compatibility (Task 0 Step 1) — BLOCK rather than force if unresolved.
