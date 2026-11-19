# Flight Requirements and Fleet Model Picker: Design

Status: approved by owner. Date: 2026-11-19.

## Intent

Currency rules only support a rolling "last N days" window. Supervisors also hand out assignments tied to a calendar period: "fly 1 hour in October", "fly each aircraft type for 15 minutes this quarter". These change from month to month and unit to unit, so they must be fully configurable from Settings without a release.

Separately, the currency rule form takes the vehicle model as free text. A typo silently makes a rule match no flights. Models should be picked from the fleet instead.

## Goals

- A new **Flight Requirements** feature for fixed-period assignments, separate from currency.
- Requirements can use a calendar month, quarter or year, a fiscal quarter or year, a monthly window between two days of the month, a span of N days, weeks or months from a start date, a custom date range, or every N months from a start date.
- Requirements can limit which flight time counts to a time of day: a clock window (including ones that cross midnight) or night as defined by civil twilight.
- Requirements can be one-time or recurring.
- Targets can be hours and minutes, a number of flights, or both.
- Aircraft scope is chosen by toggling the models in the fleet, with the option to require the target on each model separately.
- Every past period's result per pilot is kept as history.
- The free-text vehicle model field on currency rules is replaced by the same fleet model toggles.

## Non-goals

- Changing how currency is evaluated (rolling window, expiry date, reminders).
- Training hours, certification tracking, or non-flight tasks.
- Per-tenant data separation.
- Pilot groups or teams.

## Anti-goals

The work has failed if any of these is true:

- Editing a requirement rewrites the result of a period that has already closed.
- A requirement silently matches no flights because of a model spelling difference.
- Requirements change the compliance score or currency in any way. Requirements have their own score, shown next to it.
- A flight that is not reviewed counts toward a requirement. The same `counted_flights_filter()` applies as for currency.
- A flight or pilot marked not to count toward unit totals counts toward a requirement. `counted_flight_clause()` applies as for unit totals.

## Currency vs. requirements

| | Currency (existing) | Flight Requirements (new) |
|---|---|---|
| Question | Is the pilot legal to fly right now? | Did the pilot meet this period's assignment? |
| Window | Rolling, last N days | Fixed calendar or custom period |
| Status | Current, Lapsed, Expires on | On track, Met, Missed, Excused |
| History | None | One saved result per pilot per period |
| Score | Compliance score (unchanged) | Its own Requirements score, next to the compliance score |
| Flights that count | Reviewed | Reviewed, and counted toward unit totals |

## Fleet model picker

Shared by the currency rule form and the requirement form.

### Source of the list

- A new endpoint, `GET /api/currency/models`, returns the distinct vehicle models in the fleet with a count of aircraft for each. Only the rule and requirement forms use it, so it is open only to users with `certifications.manage` or `requirements.manage`. Users who can only view get nothing, so turning Fleet view off for a role still hides the fleet's models and counts from that role.
- Models are de-duplicated without regard to case, matching how currency already compares models (`X10` and `x10` are one model).
- Models with only retired aircraft are hidden from the picker, unless the rule being edited already uses them. Then they show with a "no active aircraft" note so they can be removed deliberately.

### Behavior

- An **All aircraft** toggle is on by default.
- Each fleet model is a toggle chip, labeled with its aircraft count, for example "X10 (4)".
- Turning on any model turns off All aircraft. Turning off the last model turns All aircraft back on.
- Requirements only: when two or more models are selected, a choice appears:
  - **Combined**: time on any selected model counts toward one target.
  - **Each separately**: the pilot must meet the target on every selected model.
- Requirements only: an **All active models** option for "each separately" follows the fleet automatically. A model added to the fleet joins the next period, not the current one.

### Currency rule change

- `currency_rules.vehicle_model` (one string) becomes a list of models. The rule counts flights on any selected model, so it behaves like "Combined".
- The migration copies each existing single value into a one-item list. Rules with no model stay "All aircraft".
- If an existing value matches no fleet model, it is kept and flagged in the form so the admin can fix it.

## Requirement definition

| Setting | Options |
|---|---|
| Name, description | Free text |
| Period | Calendar month, calendar quarter, calendar year, fiscal quarter, fiscal year, monthly window (day X to day Y), span from a start date (N days, weeks or months), custom date range, every N months from a start date |
| Repeats | One time, or recurring with an optional end date |
| Starts | The first period (for example, October 2026 or Q4 2026) |
| Target | Hours and minutes, flights, or both |
| Aircraft | Fleet model picker, with Combined or Each separately |
| Time of day | Any time (default), clock window, or night (civil twilight) |
| Flight purposes | All purposes (default), or selected purposes as toggle chips. Flights with no purpose count only under All |
| Applies to | All active pilots, or selected pilots |
| Active | On or off |

The fiscal year start month is a unit setting, defaulting to October.

The form shows a live plain-English summary, for example:

> Every **quarter**, **all active pilots** must fly **15 min** on **each of: X10, X2E, LEMUR 2**, starting **Q4 2026**, no end date.

> Every month from the **19th to the 5th of the following month**, **all active pilots** must fly **1 hour** on **any aircraft** between **12:00 AM and 6:00 AM**, starting **Nov 19, 2026**, no end date.

### Monthly window

- Set by a start day and an end day of the month, for example the 19th to the 5th.
- When the end day is earlier than the start day, the window ends in the following month.
- A day past the end of a short month means that month's last day (the 31st in February is the 28th or 29th).
- Recurring monthly windows follow one another, so a 19th to 5th window repeats every month starting on the 19th.

### Span from a start date

- A quick way to say "the next two weeks" or "the next 3 months": a start date plus a length in days, weeks or months.
- It can repeat, for example every two weeks.

### Time of day

- **Any time**: all flight time counts. This is the default and matches currency.
- **Clock window**: a start and end time in the unit's display timezone, for example 12:00 AM to 6:00 AM, or 6:00 PM to 2:00 AM. When the end is earlier than the start, the window crosses midnight.
- **Night**: from the end of evening civil twilight to the start of morning civil twilight, the definition Part 107 uses. Sunset and sunrise are calculated for the flight's takeoff location and date. When a flight has no coordinates, the unit default location (`org_default_lat`, `org_default_lon`) is used. When neither is set, the form refuses the night option and says why.
- Only the minutes that fall inside the window count. A flight from 5:30 AM to 6:15 AM gives 30 minutes toward a 12 AM to 6 AM window.
- A flight counts toward the flight-count target when at least one of its minutes falls inside the window.
- The window applies to every day in the period. A flight that starts inside the period but runs past its end counts only up to the period's end.
- The date window and time window are independent. "12 AM to 6 AM between the 19th and the 5th" uses a monthly window for the dates and a clock window for the hours.
- To combine targets, such as 1 hour of night flight and 2 hours in total, create two requirements.

### Examples

| Assignment | Period | Repeats | Target | Aircraft | Time of day |
|---|---|---|---|---|---|
| Fly 1 hour in October | Calendar month, Oct 2026 | One time | 1h | All aircraft | Any time |
| Fly 1 hour in the next 3 months | Span from today, 3 months | One time | 1h | All aircraft | Any time |
| Fly each drone type 15 minutes per quarter | Calendar quarter, from Q4 2026 | Recurring | 15m | All active models, each separately | Any time |
| Fly 1 hour at night over the next two weeks | Span from today, 2 weeks | One time | 1h | All aircraft | Night |
| Fly 1 hour between 12 AM and 6 AM, from the 19th to the 5th of the following month | Monthly window, 19th to 5th | Recurring | 1h | All aircraft | Clock window, 12:00 AM to 6:00 AM |
| Fly 1 hour between 6 PM and 2 AM in December | Calendar month, Dec 2026 | One time | 1h | All aircraft | Clock window, 6:00 PM to 2:00 AM |

## Evaluation

- One pure function returns the period that contains a given date, `(start, end)` inclusive, for a requirement. It holds all calendar math and is tested on its own: month lengths, leap years, quarter and fiscal boundaries, and custom ranges.
- Flight dates are already local dates (migration 0008), so period boundaries use `Flight.date` directly for requirements with no time-of-day limit.
- With a time-of-day limit, each flight becomes a local interval: takeoff time converted to the display timezone, plus `duration_seconds`. Takeoff times are stored as UTC (including manual entries, which `local_flight_date` already treats as UTC) and converted with `display_zone`. Sources stored in local wall-clock time, such as Parrot logs, are used as is. The build confirms how each import source stores time (see migrations 0008 and 0010) before relying on it. A second pure function returns the minutes of an interval inside a window, and is tested on its own.
- A flight with no takeoff time cannot be placed in a time window, so it does not count toward a time-limited requirement. The pilot's progress shows how many flights were left out for this reason, so the pilot or a supervisor can add the missing time.
- Civil twilight is calculated with the `astral` library (pure Python, no network access).
- A pilot's status in the current period:
  - **Met**: the target is reached (on every model, when "each separately").
  - **On track**: not met yet, and the period is still open.
  - **Pending review**: the period has ended without the target met, and the grace period is still running.
  - **Missed**: the grace period ended without meeting the target.
  - **Excused**: a supervisor excused the pilot for this period (leave, injury, new hire).
- A pilot added partway through a period is excused for that period automatically. The supervisor can remove the excusal.

## After a miss

- A Missed result flags the pilot: an item in the pilot's Needs Attention list and on the dashboard, and a "Missed requirement" badge on the pilot list and the pilot's profile.
- The flag clears when the pilot meets the next period of the same requirement, or when a supervisor with `requirements.excuse` excuses the miss.
- A one-time requirement has no next period, so its flag clears only by excusal.
- The pilot's active or inactive status is never changed.

## History

- A period that has ended stays **Pending review** for a grace period, 14 days by default (unit setting `requirements_grace_days`). During it, results are worked out live, so a late-reviewed flight still counts. The pilot's progress and the dashboard list the unreviewed flights inside the period, so supervisors can review them before the grace period ends.
- When the grace period ends, each assigned pilot's result is saved: the hours and flights per model, the status, and a copy of the requirement's target and scope at that time.
- Saving happens when such a period is first read, and also from the existing daily scheduler. Both are safe to run twice.
- Edits to a requirement apply to the current period and later ones. Saved periods are never recalculated.
- Re-reviewing an old flight does not change a saved period. An admin can recalculate one period on purpose, and that is audited.

## Requirements score

- A separate score, shown next to the compliance score. The compliance score, its weights and currency are unchanged.
- It is the share of saved results that are **Met** out of all saved results whose period ended in the last 12 months, across every requirement and assigned pilot.
- Excused results and periods still open or pending review are left out.
- With "each separately", a pilot's period counts as one result: Met only when every model is met.
- With no saved results in the last 12 months, the score shows "No results yet" instead of a number.

## Permissions

New rows in the role permissions grid, in their own "Flight requirements" group:

| Key | Meaning | Supervisor | Pilot | Viewer |
|---|---|---|---|---|
| `requirements.view` | See requirements, every pilot's progress and history, and the Requirements score | Yes | Yes | Yes |
| `requirements.manage` | Create, edit, delete requirements; recalculate a closed period | Yes | No | Locked off |
| `requirements.excuse` | Excuse or un-excuse a pilot for a period | Yes | No | Locked off |

Admins always have all three. Anyone with view sees every pilot's progress, not only their own. Currency stays on the existing `certifications.view` and `certifications.manage` rows.

## Screens

- **Settings, Flight Requirements**: a list of requirements and the builder form above. It sits next to Currency Rules and needs `requirements.manage`.
- **Settings, Currency Rules**: shown to anyone with `certifications.manage`, not only admins, so supervisors can manage currency. The API already allows this; today only the screen is admin-only.
- **Dashboard and Compliance, Requirements score**: shown next to the compliance score. The compliance score itself does not change.
- **Dashboard, This Period card**: for each active requirement, the days left in the period, how many pilots have met it, and each pilot's progress, for example "X10 12/15m, X2E done".
- **Pilot detail, Requirements tab**: the current period's progress and a history table of past periods.
- **Pilots list and pilot profile**: the "Missed requirement" badge while a miss is flagged.
- **Settings, Currency Rules form**: the free-text model field is replaced by the fleet model picker.

## Data model

- `flight_requirements`: definition (name, description, period type, period parameters, repeats, start, end, target hours, target flights, model mode, time-of-day mode, window start time, window end time, active, timestamps, created and modified by).
- `flight_requirement_models`: requirement id and model name. No rows means all aircraft.
- `flight_requirement_pilots`: requirement id and pilot id. No rows means all active pilots.
- `flight_requirement_purposes`: requirement id and purpose name. No rows means all purposes.
- `flight_requirement_results`: requirement id, pilot id, period start, period end, status, totals per model (JSON), target snapshot (JSON), excused by and reason, saved at. Unique on requirement, pilot and period start.
- `currency_rule_models`: rule id and model name, replacing `currency_rules.vehicle_model`.

One additive migration, 0016. The old `vehicle_model` column is kept for one release after its values are copied, then dropped in a later migration.

## API

- `GET /api/currency/models`
- `GET, POST /api/requirements`, `PATCH, DELETE /api/requirements/{id}`
- `GET /api/requirements/status`: current period for all assigned pilots
- `GET /api/requirements/pilots/{pilot_id}`: current period and history for one pilot
- `POST /api/requirements/{id}/excuse`: excuse or un-excuse a pilot for a period
- `POST /api/requirements/{id}/recalculate`: recalculate one closed period (audited)

All write routes are audited like currency rules.

## Testing

- Period math: every period type, around month, quarter, fiscal and year boundaries, February in leap and non-leap years, monthly windows that end in the following month, and end days past a short month.
- Time windows: windows that cross midnight, flights that start before and end inside a window, flights longer than a window, flights spanning two nights, and daylight saving changes.
- Night: twilight times checked against published values for a known location and date, the unit default location used when a flight has no coordinates, and the night option refused when neither exists.
- Flights with no takeoff time are left out of time-limited requirements and reported.
- Model matching ignores case, and "each separately" fails when any one model is short.
- Only reviewed flights count, and flights or pilots excluded from unit totals do not. Reviewed flights with an unconfirmed pilot match count.
- A purpose filter counts only flights with a selected purpose; flights with no purpose count only with All purposes.
- A miss flags the pilot until the next period is met or the miss is excused; a one-time miss clears only by excusal.
- Closed periods do not change after a requirement is edited or a flight is re-reviewed.
- A period stays Pending review through the grace period; a flight reviewed inside it counts, and one reviewed after it does not.
- Requirements never change the compliance score or currency results.
- The Requirements score covers 12 months, leaves out excused and pending results, and shows "No results yet" when there are none.
- Supervisors can manage currency rules and requirements in Settings; the new permission rows gate every requirement route.
- The currency migration keeps each existing rule's behavior exactly as before.
- Permission coverage tests include every new route.

## Resolved questions

1. Pilot groups: not needed. Requirements target all active pilots or selected pilots.
2. "Fly 1 hour in the next 3 months" is confirmed as 3 months, as in the examples table.
3. Compliance: requirements never feed the compliance score or currency. They get their own Requirements score next to it, over a rolling 12 months (2026-11-18).
4. Late reviews: a 14-day grace period after a period ends before results are saved, adjustable in Settings (2026-11-18).
5. Flights excluded from unit totals (`counts_toward_totals`, on the flight or the pilot) do not count toward requirements (2026-11-18).
6. Permissions: own rows `requirements.view`, `requirements.manage`, `requirements.excuse`; anyone with view sees all pilots' progress (2026-11-18).
7. Supervisors manage both currency rules and requirements; the Currency Rules screen opens to `certifications.manage` (2026-11-18).
8. Fleet data: the two X2 aircraft with model `E1` are corrected to `X2E` by the owner before the picker ships (2026-11-18).
9. Flights with an unconfirmed pilot match (`pilot_confirmed = false`) count once reviewed, as for currency (2026-11-18).
10. Flight purpose filter: optional purpose toggles on each requirement, default all purposes (2026-11-18).
11. A miss flags the pilot (Needs Attention, dashboard, and a badge on the pilot list and profile) until the next period is met or a supervisor excuses it. Pilot status is unchanged (2026-11-18).
