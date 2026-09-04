# DUM Pre-Go-Live Master Plan

Date: 2026-06-10
Status: active. App is DEPLOYED but in a **testing phase** (not yet in
production use by any org), so breaking changes / resets are still acceptable
while we harden toward go-live. `main` @ `64ecd7b`, CI green.

This plan coordinates several workstreams. Each line notes the OWNER:
**[new-chat]** = handed off to a fresh session via its own spec (to save
context); **[this-chat]** = do in the current session; **[user]** = Jonathan;
**[ongoing]** = a habit, not a discrete task.

---

## W1 — Automated backend test suite  [new-chat]
The app has NO test framework; everything has been verified by `py_compile` +
ad-hoc smoke scripts + manual + subagent review. This is the biggest structural
gap (the login-500 and dashboard React #31 crash are exactly what a test suite
catches). Build a pytest backend suite + wire it into CI.

Handoff spec: `docs/superpowers/specs/2026-06-10-backend-test-suite.md`
(self-contained; a fresh chat executes it end-to-end). Frontend tests (Vitest)
are a later, optional phase — not in the first pass.

## W2 — Verification pass ("verify everything")  [this-chat]
Confirm the risky/deferred items from the original review actually shipped, and
spot-check security-critical paths against the live app + source:
1. **CSP** — confirm whether nginx ships `Content-Security-Policy` enforced or
   only `-Report-Only`; if Report-Only and the app is clean, flip to enforce.
2. **entity_type validation** — confirm maintenance / equipment-checkout /
   schedule endpoints validate `entity_type` + existence (was data-dependent).
3. **Spot-check** (source + live token): secret redaction on /settings + backup
   export; flight bulk-delete telemetry purge; photo link/signed-URL authz;
   the new /sync/disconnect + last_sync_result; geocode 404/502.
Output: a short findings list; fix anything broken (small) or log it as a task.

## W3 — Docs + user-manual refresh  [this-chat]
Update the in-app User Manual + README + the vault project note to match the
app as it stands. Features added since the manual was last touched: calendar,
drone locations + org default location, equipment checkouts, per-pilot
needs-attention, richer Skydio sync status + disconnect, sidebar drag-reorder,
CommandPalette filter, Airspace recent-location. Note the deploy model changed
(Alembic-managed; normal `docker compose pull && up -d`, no reset).

## W4 — Go-live prep  [this-chat + user]
The blockers before real org use:
1. **Pilot accounts + permissions** — create real logins for the unit; verify
   supervisor vs pilot role gating holds on the sensitive endpoints. [this-chat
   builds/verifies; user creates the real accounts]
2. **Automated backups** — scheduled `/app/data` (DB + uploads) backup now that
   Alembic owns the schema; document restore. [this-chat designs; user wires
   the host cron / Unraid task]
3. **Final security/correctness pass** — once W1 tests exist, a focused review
   of auth + upload + backup before real data lands. [this-chat, after W1]

## W5 — Ops hygiene  [ongoing]
- **Base-image digest bumps** — re-resolve node/python digests when patches
  land (monthly or on a Trivy flag); update the two Dockerfile `FROM` lines.
- **Alembic discipline** — every future model change ships a reviewed
  `alembic revision --autogenerate`; never hand-edit the live schema.

---

## Suggested sequence
1. **W2 verify** (this chat) — fast, read-only, gives confidence + a punch list.
2. **W3 docs refresh** (this chat) — while context is fresh.
3. **W1 test suite** (new chat) — hand off the spec; it's the big build.
4. **W4 go-live prep** (after W1) — accounts/permissions + backups + final pass.
5. **W5** — ongoing, no scheduled action.

Deploy of `64ecd7b` (normal pull) is independent and can happen any time. [user]
