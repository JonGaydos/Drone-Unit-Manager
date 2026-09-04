# Frontend Test Suite — Design Spec

Date: 2026-06-15
Status: ready to plan. Self-contained. This is the "later phase" of testing named
in `docs/superpowers/specs/2026-06-10-backend-test-suite.md` and workstream W1's
follow-on. The backend pytest suite (71 tests) already shipped; this adds an
exhaustive **Vitest** frontend suite. Playwright **E2E is a separate next phase**,
not this one.

## Why

The frontend (`frontend/`, React 19 + Vite 8 + Tailwind 4, react-router 7) has
**no automated tests**. The dashboard React #31 crash (an object rendered raw into
JSX) is exactly the class of bug a component render test catches. Goal: exhaustive
component/unit coverage of the whole frontend, wired into CI, so refactors and new
features are guarded. Coverage target is maximal ("every possible test"): units,
the API client, contexts, hooks, all components, and all 37 pages.

## Environment / conventions

- `frontend/` is npm-managed (`package-lock.json`). Install test deps with **npm**
  (do NOT switch package managers). React 19, Vite 8, Tailwind 4.
- Path alias `@` → `frontend/src` already exists in `vite.config.js`; Vitest reuses
  the same config (react plugin + alias), so no duplicate alias setup.
- All backend calls flow through `@/api/client` (`src/api/client.js`), a `fetch`
  wrapper: attaches `Authorization: Bearer <localStorage token>`, redirects to
  `/login` once on 401 (`handleUnauthorized`/`resetSessionExpired`), 30s timeout via
  `AbortController`, returns `null` on 204, sanitizes error bodies (strips
  `SQL`/`Traceback`/`/app/`), and parses `Content-Disposition` filenames.
- Contexts: `AuthContext` (user, login/logout/updateUser, role booleans
  isAdmin/isSupervisor/isPilot/isManager/isViewer, validates `/auth/me` on mount),
  `ThemeContext`, `ToastContext`.
- Run from `frontend/`. Tests run against the CI/dev Node interpreter, never a
  browser; jsdom is the DOM environment.
- Git discipline (CLAUDE.md): branch `tests/frontend-suite` off main, execute via
  subagent-driven development, merge `--ff-only`, push only when asked.

## Mocking strategy: MSW (network layer)

Use **Mock Service Worker** (`msw`) to intercept `fetch` at the network boundary.
This runs the **real** `api/client.js` (so its 401/timeout/204/sanitization/
Content-Disposition logic is exercised inside page tests) and gives pages realistic
HTTP responses. Per-test overrides via `server.use(...)` cover empty/error/edge
cases. jsdom-incompatible libraries are mocked at the module level (see Batch 0):
`react-leaflet`+`leaflet`, `@fullcalendar/*`, and `recharts` → lightweight stub
components rendering an identifiable placeholder. Do NOT module-mock `@/api/client`
itself (that would bypass the very logic we want covered).

## Test infrastructure (`frontend/src/test/`) — Batch 0, build first

- **Dependencies** (devDependencies, npm): `vitest`, `@vitest/coverage-v8`,
  `jsdom`, `@testing-library/react`, `@testing-library/user-event`,
  `@testing-library/jest-dom`, `msw`.
- **`vite.config.js`**: add a `test` block — `environment: 'jsdom'`,
  `globals: true`, `setupFiles: ['./src/test/setup.js']`, `css: true`, and v8
  coverage (exclude `src/test/`, `src/main.jsx`, `**/*.config.js`). Keep existing
  plugins/alias/build/server untouched.
- **`package.json` scripts**: `test` (watch), `test:run` (single pass for CI),
  `test:coverage`.
- **`src/test/setup.js`**: import `@testing-library/jest-dom`; start MSW server
  (`beforeAll` listen with `onUnhandledRequest: 'error'`, `afterEach`
  `resetHandlers()` + RTL `cleanup()` + `localStorage.clear()`, `afterAll` close);
  polyfill jsdom gaps (`matchMedia`, `ResizeObserver`, `IntersectionObserver`,
  `URL.createObjectURL`/`revokeObjectURL`, `Element.prototype.scrollTo`); register
  the global module mocks for leaflet/fullcalendar/recharts.
- **`src/test/server.js`** + **`src/test/handlers.js`**: MSW `setupServer` with
  default handlers (at minimum `GET /api/auth/me`); tests override per-case.
- **`src/test/render.jsx`**: `renderWithProviders(ui, { route = '/', user, role })`
  — wraps `MemoryRouter` (initialEntries from `route`) + `AuthProvider` +
  `ThemeProvider` + `ToastProvider`; when `user`/`role` is supplied, seed
  `localStorage` `token` + `user` so the auth mount path resolves; return the RTL
  result plus a `userEvent` instance. Provide a `renderRoute` variant for tests
  that need router params (detail pages).
- Batch 0 ends with one smoke test proving the harness renders a trivial component
  through the providers and an MSW-backed `api.get` call resolves.

## Coverage inventory (execution batches)

Each batch is dispatched as a fresh subagent (isolated context) during execution.
Batch 0 (above) is the gate. Order 1→10 after that; pages can run in any order once
the harness exists.

1. **lib/** — `formatters` (formatDuration, formatHours, metersToFeet, mpsToMph,
   formatDate, daysUntil, formatDateTime, normalizeDateValue: assert null/empty/zero
   handling, unit conversions, and date edge cases incl. month boundaries),
   `utils` (cn class-merge precedence, sortByName/sortByField/sortPilots/
   sortVehicles/sortPilotsActiveFirst stability, vehicleDisplayName/
   equipmentDisplayName fallbacks, formatStatusText), `location`
   (resolveOrgLocation with/without settings + DEFAULT_ORG_LOCATION fallback),
   `a11y` (interactiveProps), `constants` (shape/keys — light).
2. **api/client** — happy path for get/post/patch/put/delete via MSW; 401 clears
   localStorage + redirects exactly once + `resetSessionExpired` re-arms; timeout →
   "request timed out" message; 204 → null; empty body → null; error sanitization
   (string detail passthrough, array detail joined, SQL/Traceback/`/app/` → generic);
   `parseFilename` exercised via `download`/`downloadPost` (RFC 5987, legacy quoted/
   bare, fallback); `upload` error handling. Stub `location.href` and
   `URL.createObjectURL` as needed.
3. **contexts + hooks** — `AuthContext`: login stores token + sets user, logout
   clears, updateUser merges, role booleans correct for each role
   (admin/supervisor/pilot/manager/viewer), `/auth/me` validates on mount (success
   sets user; failure clears token), `useAuth` throws outside provider.
   `ThemeContext` (toggle + persistence + system preference via matchMedia mock),
   `ToastContext` (add/remove/auto-dismiss with fake timers). `useConfirm`
   (resolve on confirm, reject/false on cancel), `useViewTransition` (calls
   document.startViewTransition when present, falls back when absent).
4. **ui components** — Button (variants/disabled/onClick), Modal (open/close via
   close button, Escape, overlay click; focus/scroll lock if present), ConfirmDialog
   (confirm/cancel callbacks), DataTable (renders rows, sort toggle, empty state),
   Input + Select (value/onChange, associated label/a11y), Badge + StatCard (render
   by status/props), Card, PageErrorBoundary (renders fallback when a child throws,
   not a white screen).
5. **layout + feature** — Layout (renders nav + child outlet), Sidebar (role-gated
   links: admin sees admin-only entries, pilot/viewer do not; active-route
   highlight), TopBar (search/command-palette trigger, user menu + logout calls
   AuthContext.logout); CommandPalette (opens on Ctrl+K, filters, navigates on
   select), FlightMap (renders with mocked leaflet; graceful with no/invalid coords),
   LinkedPhotos (lists, link/unlink call the API), ImportMappingModal (column
   mapping UI + submit), DocumentUpload (file select → upload call, error path).
6–10. **pages (37)** — five batches of ~7–8 pages grouped by area:
   - **6 auth/dashboard/home:** Login, SetupPage, DashboardPage, FleetHealthPage,
     NotFoundPage, UserManualPage, AuditLogPage.
   - **7 fleet/equipment:** FleetPage, VehicleDetailPage, BatteryDetailPage,
     ControllerDetailPage, DockDetailPage, SensorDetailPage, AttachmentDetailPage,
     MaintenancePage.
   - **8 flights/ops:** FlightsPage, FlightDetailPage, FlightPlansPage,
     IncidentPage, MissionLogPage, TrainingLogPage, ChecklistPage.
   - **9 pilots/compliance:** PilotsPage, PilotDetailPage, CertificationsPage,
     CompliancePage, CheckoutsPage, AlertsPage.
   - **10 settings/misc:** SettingsPage, IntegrationsPage, AnalyticsPage,
     CalendarPage, AirspacePage, WeatherPage, MediaPage, DocumentStoragePage,
     ReportsPage.

   **Per-page baseline (all pages):** renders under providers + MSW without
   crashing; loading state resolves to data; empty state (MSW returns empty);
   **error state — MSW 500 yields an error UI, not a white screen / unhandled
   throw.** Detail pages render with a route param and a mocked entity.

   **Richer interaction tests (incident-prone / high-traffic):**
   - **LoginPage:** submit calls auth login, success navigates, bad creds show error.
   - **DashboardPage:** explicit **React #31 regression** — object-valued fields
     (e.g. weather/station) must render as text, never an object raw into JSX; the
     page must not crash on a fully-populated dashboard payload.
   - **FlightsPage:** filtering and bulk actions (select + bulk-delete/update call
     the API).
   - **SettingsPage:** secret fields render redacted; save flow.
   - **PilotsPage / IncidentPage:** primary create/edit interaction.

## CI integration

Add a second job `frontend` to the existing `.github/workflows/tests.yml`
(alongside the backend `pytest` job — one workflow, two independent jobs):
- checkout (reuse the repo's pinned `actions/checkout` SHA) → `actions/setup-node`
  (SHA-pinned, Node 22, `cache: npm`, `cache-dependency-path: frontend/package-lock.json`)
  → `npm ci` in `frontend/` → `npm run test:run`.
- **Non-gating** relative to the image build (its own workflow), matching the
  backend suite. Pin every `uses:` to a 40-char commit SHA with a version comment,
  matching `docker-publish.yml` convention.

## Verification (of the suite itself)

- `cd frontend && npm run test:run` passes locally (all tests green).
- The `frontend` CI job is green.
- Report coverage by area (which batches done) and any real app bugs the tests
  surfaced (treat as findings to fix or log, like W1 — e.g. a page that crashes on
  a valid payload, a missing empty/error state, an unsanitized error).

## Out of scope (this phase)

- Playwright/E2E browser tests (the next phase).
- Visual-regression / screenshot tests.
- Performance / bundle-size tests.
- Deep accessibility audits (basic role/label assertions only).
- Testing third-party libraries themselves (leaflet, fullcalendar, recharts are
  stubbed).
- Backend changes; modifying the Docker image with test deps (CI/dev only).
