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
