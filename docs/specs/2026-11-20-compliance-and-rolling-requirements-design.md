# Compliance and Rolling Requirements: Design

Status: approved by owner in conversation, 2026-11-20. Builds on `2026-11-19-flight-requirements-design.md` (Flight Requirements) and replaces the currency feature.

## Intent

Flight Requirements turned out to be the better model for "is the unit flying enough". Currency (rolling rules, its own status, reminders and score points) is removed, and Flight Requirements take its place everywhere, including the compliance score. Requirements and the compliance dashboard are one subject, so they become one page.

## Decisions

| Topic | Decision |
|---|---|
| Currency | Removed completely: rules, evaluation, status, reminders, dashboard tile, pilot card, Settings card, API routes and tables |
| Rolling windows | Flight Requirements gain a **Rolling** period type: "N days, weeks or months back from today" |
| Rolling status | Checked every day: each assigned pilot is **Current** (with the date they would lapse) or **Lapsed** |
| Rolling history | Each lapse is saved with the date it started and, once the pilot is current again, the date it ended |
| Compliance score | Flight Requirements take currency's 15 points |
| Score rule | A pilot costs points when they missed the most recently closed period of any active periodic requirement, or are lapsed on any active rolling requirement right now. Deduction = (such pilots / active pilots) x 15. Excused pilots do not count. Nothing is deducted while there is no active requirement |
| Separate Requirements score | Stays as a 12-month history figure on the Compliance page; it no longer has its own place on the dashboard header |
| Page | One **Compliance** page with three tabs: Overview, Flight Requirements, Setup |
| Sidebar | One Compliance entry; no separate Flight Requirements entry |
| Currency API | Removed outright; nothing outside the app uses it |
| Release | 3.6.1 (owner's choice) |

## Rolling requirements

- Definition: period type `rolling`, window length from the existing span fields (`span_length` 1 to 365 with `span_unit` days, weeks or months). Start date is when tracking begins; no end date, no recurring flag (always continuous). Targets, aircraft scope (including Each separately and All active models), purposes, time of day and pilots work as for other types.
- Evaluation, for a given day: the window is the N units ending that day. A pilot is Current when every required target is met inside the window, else Lapsed. When Current, the lapse date is the day the oldest flight still needed would age out of the window (the same idea as currency's expiry date). Time-of-day windows and the counting rules (reviewed, counted toward unit totals) are the same as for other types.
- Grace: the period grace days do not apply to rolling requirements (there is no closing period). A flight reviewed late counts as soon as it is reviewed.
- Pilots added after tracking began are not lapsed until one full window has passed since they were added or the requirement started, whichever is later. Until then they show as **Not yet due**.
- Excusal: a supervisor can excuse a pilot from a rolling requirement until a chosen date (leave, injury). While excused the pilot is neither current nor lapsed, and costs no points.
- History: a lapse is recorded when the daily job (or a page load) first sees a pilot lapsed, and closed when it first sees them current again. Lapses are never edited by later reviews; an admin can delete a lapse record (audited) if it was caused by data later corrected.
- Notifications (only when requirement emails are on): a reminder `reminder_days` before the projected lapse date, a lapse email to the pilot and managers when a lapse starts, nothing on recovery. Digest: currently lapsed pilots.
- Outputs: Needs Attention item while lapsed; pilot list badge while lapsed; dashboard tile shows each rolling requirement with "N current, M lapsed" and each pilot's status and lapse date; CSV and PDF report include lapse records; calendar shows no deadline (none exists).

## Compliance page

- **Overview tab:** the compliance score with a breakdown of where points were lost; the stat cards (Out of Currency becomes Missed or lapsed requirements); a This Period section (current progress per requirement, periodic and rolling); Items Requiring Attention.
- **Flight Requirements tab:** the requirement list with progress, Switch on/off, edit, duplicate, save as template, CSV. Everyone with Flight requirements View sees it; changes need Manage.
- **Setup tab** (Manage only): templates and requirement settings (grace days, fiscal year start, requirement emails).
- Old links (`/requirements`, `/settings?tab=requirements`) redirect to the matching Compliance tab.

## Removed with currency

Dashboard Currency Risk tile; pilot Currency Status card; Settings Currency Rules card and modal; Compliance Currency Status section and Send currency reminders; Needs Attention currency items; currency routes and token area entry; `currency_rules` and `currency_rule_models` tables; the permission row is renamed from "Certifications and currency" to "Certifications" (keys unchanged); manual topics and checklist section 38 are replaced.

## Data

Migration 0018 (needs owner approval before it is created or run):
- adds `flight_requirement_lapses` (requirement id, pilot id, lapsed_on, recovered_on nullable, created and updated stamps; unique on requirement, pilot and lapsed_on) and `flight_requirement_excusals` for rolling excusals (requirement id, pilot id, excused_until, reason, excused by, timestamps), or reuses an existing table if the plan finds one fits;
- drops `currency_rule_models` and `currency_rules` (production has no rules; nothing is lost);
- downgrade recreates the currency tables empty and drops the new tables.
Backups include the new tables; restoring an older backup skips the currency tables.

## Testing focus

- Rolling: windows across month ends and DST, the lapse date, a pilot added mid-window, excusal until a date, lapse recorded once and closed once, late review.
- Score: periodic latest-closed-period misses and rolling lapses combined per pilot (a pilot counts once), excused pilots, no active requirements means no deduction, other score parts unchanged.
- Removal: no route, page, tile, email or permission still refers to currency; old backups restore; migration up and down.
- Page: tabs per role, redirects, deep links from the calendar and dashboard.

## Interface improvements in the same release (owner, 2026-11-20)

### Fixed page header
The top bar (page title, search, theme) stays in place on desktop while the content below it scrolls, as the sidebar already does. The phone top bar is already fixed and stays as it is.

### Arrangeable dashboard and analytics
- An **Edit layout** button on the Dashboard and on Analytics switches to edit mode: each tile gets a drag handle and an on/off switch, tiles snap into the same row grid, and tiles keep their current widths. **Save**, **Cancel** and **Reset to default**.
- Drag and drop uses `@dnd-kit` (keyboard and touch support). Keyboard users can move a tile with arrow keys in edit mode.
- **Each user has their own layout**, saved to their account so it follows them between devices. An admin can save the current layout as the **unit default** that users without their own layout get, and that Reset to default returns to.
- A tile the user cannot see (permission) is never shown, whatever the layout says. A tile added in a later release appears at the end, switched on.
- Storage: two JSON columns on `users` (`dashboard_layout`, `analytics_layout`, nullable = use the default), written through `PATCH /api/auth/me`; the unit defaults are two settings keys written by admins. Added to migration 0018.

### Flights selection bar
The selection bar (count, reassign pilot, set purpose, delete) is always shown above the table for users who can review flights. With nothing selected it reads "0 selected" and its controls are disabled; ticking a row only updates it, so nothing shifts. It stays visible just under the fixed header while a long list scrolls.

### Certifications views
A view switch at the top of the Certifications page, remembered per device:
- **Matrix:** the current grid with the pilot column and the certification header pinned while scrolling, and each cell a colored status icon (date on hover or tap).
- **By pilot:** one card per pilot with their certifications as status chips. Default on phones.
- **By urgency:** Expired, Expiring within 30, 60 and 90 days, then Current, each a list of pilot and certification with the date.
Filters (status, pilot search, hide empty) and actions (assign, edit, renew, bulk renew) work in every view where they apply.

### Flight distance and landing location (owner, 2026-11-20)
On staging data no flight had a distance or a landing location, and none had an operating cost. Distance and landing location are now worked out from GPS telemetry: distance is the length of the track (bad fixes and impossible jumps skipped), landing coordinates are the last good fix, and the landing address is looked up the same way takeoff addresses are. This runs when telemetry syncs or imports, and once in the background for existing flights. A value someone typed in is never overwritten. Flights without telemetry stay blank. A flight with a takeoff time and duration but no landing time gets landing time = takeoff + duration.

### Operating cost (owner, 2026-11-20)
Each aircraft gets an hourly operating cost (fleet record, optional). A flight's cost is its hours times its aircraft's rate, shown as an estimate, unless a cost was entered on the flight, which wins. Reports total the costs. The cost is worked out when shown, so a changed rate also changes past flights' estimates. Stored as `vehicles.hourly_operating_cost` (Float, nullable), added to migration 0018.
