# UX batch + Trivy pre-push gate — Design & Plan

Date: 2026-06-07
Status: approved (build). Scope decided with user: duplicate = 3 missing fields;
modals = ALL form modals; reports already done -> save-on-change tweak; Trivy
pre-push gating.

## A. Duplicate flight carries the 3 dropped fields (frontend, tiny)
The FlightsPage row "Copy" (FlightsPage.jsx:601-606) seeds a new flight with
pilot/vehicle/purpose/address/battery/sensor/`attachment_top`/`attachment_bottom`
but drops `attachment_left`, `attachment_right`, `carrier` (the FlightDetailPage
duplicate already carries those). Add those three keys to the row-Copy `setModal`
object so the two duplicate paths match. Verify FlightModal accepts/pre-fills
them (FlightDetailPage already passes them, so it does).

## B. Reports remember config — already implemented; minor tweak
ReportsPage already loads `dum_report_config` on mount (52-61) and saves on
Generate (130). Enhancement: also persist when the config CHANGES (so an
un-generated selection survives a reload). Add a small effect that writes the
same `{reportType,dateFrom,dateTo,selectedPilots,selectedVehicles}` to
localStorage whenever those values change. Keep the existing on-Generate save
(harmless). No behavior change beyond persistence.

## C. Consolidate ALL form modals to the shared Modal (frontend, the bulk)
Shared `components/ui/Modal.jsx` API: `<Modal open onClose title children className>`
(focus trap, Escape, backdrop click, scroll lock, role=dialog/aria-modal). For
each bespoke modal below, replace the hand-rolled `fixed inset-0` overlay +
panel with `<Modal open={...} onClose={...} title="...">{body}</Modal>`, keeping
the existing form state, submit handler, and reset-on-close behavior.

Inventory (form modals to convert):
- FlightsPage.jsx:57-165 — Add/Duplicate Flight (FlightModal component)
- PilotsPage.jsx:35-114 — Add/Edit Pilot; :129-180 — Merge Pilot
- SettingsPage.jsx:1181-1220 — Currency Rule; :1271-1330 — Edit User
- FleetPage.jsx:32-116 — Add/Edit Fleet Item; :601-650 — Merge Fleet Item
- ChecklistPage.jsx:69-143 — Add Template; :241-370 — Execute; :378-460 — View Completion
- MissionLogPage.jsx:53-152 — Add/Edit Mission
- TrainingLogPage.jsx:56-180 — Add/Edit Training
- IncidentPage.jsx:87-242 — Add/Edit Incident; :246-290 — Resolve Incident
- CertificationsPage.jsx:28-71 — Add Cert Type; :145-290 — Assign Cert; :703-750 — Bulk Renew
- BatteryDetailPage.jsx:384-450 — Record Battery Health
- MediaPage.jsx:380-430 — Photo Info Edit; :534-600 — Filter Modal

EXCLUDE (do NOT convert): MediaPage fullscreen lightbox (:260-320, z-[100], not a
form), CommandPalette, ImportMappingModal, LinkedPhotos (custom behavior; keep
separate per review).

Per-modal rules:
- Preserve the submit handler and that the form still submits (don't let Modal's
  focus trap/Escape break Enter-to-submit; the body keeps its own `<form>`).
- Preserve reset-on-close: call the page's existing reset in `onClose` (and keep
  onClose idempotent — don't trigger state thrash).
- Use Modal's `title` for the header; move the existing header text there and
  drop the bespoke header markup. Pass `className` only if a width tweak is
  needed (Modal applies className to the content panel, not the overlay).
- Some modals nest a second confirm (merge) — keep their internal logic; only the
  outer overlay/panel becomes Modal.
- If a modal has a custom max-width, pass it via `className`.

## D. Trivy pre-push gate (CI) — .github/workflows/docker-publish.yml
Reorder so a CRITICAL blocks publication. Single-arch (no `platforms:`) so
`load:true` works.
1. Keep Extract metadata.
2. Build step: `push: false`, `load: true` (image loaded to the runner daemon),
   keep cache-from/to. id=`build`.
3. Trivy GATE step on the loaded image (`image-ref` = first tag): `severity: CRITICAL`,
   `ignore-unfixed: true`, NO `exit-code: 0`, NO `continue-on-error` -> fails the
   run on a fixable CRITICAL (baseline is clean post jose 3.4.0).
4. Keep a non-blocking HIGH,CRITICAL report step too (optional; table) for
   visibility.
5. Push step: a second `build-push-action` with `push: true`, same context/tags/
   cache (cache hit -> seconds). id=`push`.
6. Lowercase image ref (unchanged).
7. cosign + SBOM: switch the digest reference from `steps.build.outputs.digest`
   to `steps.push.outputs.digest` (the pushed image's digest).
Net: build -> scan(block) -> push -> sign/SBOM. A CRITICAL now prevents the push
entirely.

## Verification
- Frontend: `npm run build` (once, centrally) succeeds; `eslint` on changed files
  — no NEW errors vs baseline. Manual spot-reasoning: each converted modal still
  opens/closes, submits, and resets. (No automated UI tests exist.)
- CI (D): the run goes green (build -> scan passes on the clean baseline -> push
  -> sign -> SBOM). Confirm cosign/SBOM use the push digest and succeed.
- Live (user): open a few converted modals (add flight, edit pilot, assign cert)
  — submit + Escape + backdrop-close behave; duplicate a flight -> left/right/
  carrier carry; reports config persists across reload.

## Build protocol (avoid parallel races)
Two frontend implementers on DISJOINT files (no shared file) + one CI implementer,
in parallel. Implementers: edit only their assigned files; run `npx eslint <their
files>` (safe); do NOT run `npm run build` (central, avoids dist/ races); do NOT
`git stash`/`git checkout`/commit (orchestrator commits centrally).
- FE-1: FlightsPage (modal + duplicate A), PilotsPage, SettingsPage, FleetPage, ReportsPage (B).
- FE-2: ChecklistPage, MissionLogPage, TrainingLogPage, IncidentPage, CertificationsPage, BatteryDetailPage, MediaPage (info+filter, NOT lightbox).
- CI: docker-publish.yml (D).
