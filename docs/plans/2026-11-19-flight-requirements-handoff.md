# Flight Requirements: Session Handoff

Date: 2026-11-19. From: cloud session. To: local Claude Code session with vault access.

## Where things stand

- Branch: `ccr-8a9ed482-y8kuri`. It holds only the spec and this handoff. No code or schema has changed.
- Spec: `docs/specs/2026-11-19-flight-requirements-design.md`. Read it in full before anything else.
- Nothing is built. Do not start building until the steps below are done and Jon confirms the build order.

## Decisions already made (do not reopen unless Jon raises them)

- Flight Requirements is a new feature, separate from currency. Currency evaluation, expiry and reminders stay as they are.
- Vehicle models are chosen with toggles built from the fleet, on both the currency rule form and the requirement form. This replaces the free-text model field.
- Periods: calendar month, quarter and year; fiscal quarter and year (start month is a setting, default October); monthly window (day X to day Y, rolling into the next month); span from a start date (N days, weeks or months); custom range; every N months.
- Time of day: any time, clock window (may cross midnight), or night by civil twilight using the takeoff location, falling back to `org_default_lat` and `org_default_lon`.
- Only minutes inside a time window count. A flight counts toward a flight-count target if any part is inside the window. Flights with no takeoff time are left out of time-limited requirements and reported.
- Combined targets (night hours plus total hours) are two separate requirements.
- No pilot groups. A requirement targets all active pilots or selected pilots.
- "Fly 1 hour in the next 3 months" is confirmed as 3 months.
- Requirements do not affect the compliance percentage or reminders unless that is turned on per requirement.
- Closed periods are saved as snapshots and never recalculated by edits.

## Open decision

Build order. Recommended: the fleet model picker for currency rules first, as its own change, then Flight Requirements as a second change. The alternative is everything at once. Ask Jon.

## Step 1: Review the vault

Read the vault notes for Drone Unit Manager and anything they link to. Look for:

- Project conventions: merge gate, SonarCloud rules, staging-first releases, PR and review process, test commands, release and Unraid deploy steps.
- Open bugs, backlog items or ideas that touch currency, pilots, flights, fleet models, takeoff times, timezones, the dashboard, notifications or the role permissions grid.
- Anything that conflicts with the spec, or that the spec should absorb.
- Unit context that affects the design, such as how night operations, training and assignments are actually run. Use policy and process notes only. Do not read or ask for case details, rosters tied to cases, reports or personal identifiers.

Also read `docs/LESSONS_LEARNED.md` and `docs/TEST_CHECKLIST.md` in the repo.

Report what you found as a short list, grouped as: conflicts with the spec, issues worth fixing, ideas worth adding. Do not edit or delete vault notes without Jon's approval.

## Step 2: Check SonarCloud

Pull the project's current open issues and quality gate status. Note any that sit in files this work will touch (`backend/app/routers/currency.py`, `backend/app/models/currency_rule.py`, `frontend/src/pages/SettingsPage.jsx`, `frontend/src/pages/CompliancePage.jsx`, `frontend/src/pages/PilotDetailPage.jsx`). New work must add zero new issues.

## Step 3: Ask Jon about gaps in the plan

Ask one or two questions at a time, not a list. Lead with a recommendation for each. Starting points the cloud session found but did not raise:

1. **Late reviews.** Only reviewed flights count. A flight flown on the last night of a period may not be reviewed until days later. Should snapshots wait for a grace period (for example 7 days after the period ends), or close immediately?
2. **Permissions.** The spec reuses `certifications.view` and `certifications.manage`. Should requirements get their own keys in the role permissions grid (for example `requirements.view`, `requirements.manage`, `requirements.excuse`), and can pilots see their own progress?
3. **Which flights count.** Should a requirement be able to filter by flight purpose (training only, missions only)? Should flights marked not to count toward totals (`counts_toward_totals`) or not confirmed by the pilot (`pilot_confirmed`) count?
4. **Notifications.** Email when a pilot is assigned, a reminder some days before a period ends, inclusion in the existing email digest?
5. **Consequences of a miss.** Is a missed requirement only a record, or should it flag the pilot somewhere (dashboard alert, pilot status)?
6. **Records.** Does the unit need a PDF or CSV export of period results for training files or audits?
7. **Calendar.** Should requirement periods and deadlines appear on the existing calendar page?
8. **Reuse.** Is a "duplicate requirement" or template option needed for monthly assignments that change slightly each month?
9. **Flights outside the home timezone**, such as mutual aid in another zone. Are clock windows always in the unit's display timezone, or the local time where the flight happened?
10. **Night fallback.** Is the unit default location set in Settings today? The night option depends on it for flights without coordinates.

Record each answer in the spec, commit, and push to the branch.

## Step 4: Before building

- Confirm the build order with Jon.
- The work includes a database migration (0016). Get Jon's explicit approval before creating or running it.
- Write an implementation plan in `docs/plans/` in the same style as `2026-11-02-role-permissions.md`, and have Jon approve it.
- Follow the vault's conventions for branches, PRs, CI, SonarCloud and staging.
