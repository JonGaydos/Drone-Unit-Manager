# Checkouts Page + UX Polish — Design

Date: 2026-06-06
Project: Drone Unit Manager (FastAPI + React + SQLite)
Status: approved (build as one batch)

## Context

The unit wants equipment checkouts on their own page instead of buried in the
Vehicle Detail page, plus a set of small UX improvements surfaced by the code
review. Shipped as one batch.

## Feature 1 — Dedicated Checkouts page

The `equipment-checkouts` backend already supports everything needed (list with
filters, `/active`, create with double-checkout 409, `/{id}/checkin`, supervisor
delete, pilot-name enrichment) for all six equipment types
(`vehicle, battery, controller, dock, sensor, attachment`). **No backend
changes.**

- New route `/checkouts` + sidebar entry under the "Fleet & Crew" group.
- Page sections:
  1. **Active checkouts** — table of items currently out: equipment (type +
     name), holder (`checked_out_by_name`), checked-out date, expected return,
     with a **Check In** action per row. Source `GET /equipment-checkouts?active_only=true`.
  2. **Check Out** (button → shared Modal): select equipment **type** →
     specific **item** (dropdown from that type's list endpoint) → **pilot**
     (defaults to the current user's linked pilot) → optional condition_out /
     expected_return / notes_out → `POST /equipment-checkouts`. Sends a readable
     `entity_name` (the selected item's label) so lists show names, not
     "vehicle #5". Surfaces the 409 "already checked out" as a clear message.
  3. **History** — recent checkouts (active + returned) with filters
     (entity_type / pilot / active-only) via `GET /equipment-checkouts`;
     supervisors get a delete per record (`DELETE /equipment-checkouts/{id}`).
- Equipment item lists for the Check Out dropdown come from existing list
  endpoints (`/vehicles`, and the equipment router's battery/controller/dock/
  sensor/attachment lists). Fetch the relevant list when a type is chosen.
- Permissions: any pilot checks out/in (`PilotUser`); supervisor deletes —
  enforced by the backend; the UI shows actions accordingly.

### Fleet removal

Strip the entire Checkout Status section from `VehicleDetailPage.jsx`: the
related state, the Check Out and Check In forms + their submit handlers, the
`/equipment-checkouts` fetches, the JSX block, and any now-unused imports. No
read-only remnant — checkouts live solely on the new page.

## Feature 2 — UX polish (6 small, independent items)

1. **NotFound page** — a real 404 page (message + link home) replacing the
   silent catch-all redirect in `App.jsx`.
2. **Sticky Settings save bar** — float/stick the main Save bar when
   `hasUnsavedChanges` is true (dirty-state already tracked).
3. **Richer Integrations sync status** — show last-sync result/counts + last
   error + a "sync now" affordance on `IntegrationsPage` (uses `/sync/status`).
4. **DataTable loading skeletons** — add a `loading` prop to `DataTable` that
   renders skeleton rows (existing `.skeleton` CSS) instead of "No data" while
   fetching.
5. **Standardized destructive confirms** — wire the known inline destructive
   actions that currently skip confirmation to the shared `ConfirmDialog` /
   `useConfirm`. Bounded sweep of the identified cases, not a global refactor.
6. **Reports remember-last-config** — persist the last report filter selection
   in `localStorage` and pre-fill on next visit.

## Non-goals

- No backend changes for checkouts (the API is sufficient).
- No new checkout-able entity types.
- Not a global confirmation-dialog refactor — only the known unconfirmed
  destructive actions.

## Verification

- Backend: unchanged; `import app.main` sanity only.
- Frontend: `npm run build` + `eslint`; the Checkouts page exercised live
  (check out each equipment type, double-checkout 409, check in, supervisor
  delete; confirm the Vehicle Detail page no longer shows checkout UI and still
  renders). Polish items spot-checked (404 route, sticky save bar on a dirty
  Settings form, integrations sync status, a table's loading skeleton, a
  destructive confirm fires, Reports config persists).

## Files (anticipated)

New: `frontend/src/pages/CheckoutsPage.jsx`, `frontend/src/pages/NotFoundPage.jsx`.
Modify: `frontend/src/App.jsx` (route + 404), `components/layout/Sidebar.jsx`
(nav entry), `pages/VehicleDetailPage.jsx` (remove checkout section),
`pages/SettingsPage.jsx` (sticky save bar + any confirm wiring),
`pages/IntegrationsPage.jsx` (sync status), `components/ui/DataTable.jsx`
(loading prop), `pages/ReportsPage.jsx` (remember config), plus the few files
holding the destructive actions identified for confirmation wiring.
No backend files.
