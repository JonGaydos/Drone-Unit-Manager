# Flight Requirements and Fleet Model Picker: Design

Status: draft, pending owner answers to the open questions. Date: 2026-11-19.

## Intent

Currency rules only support a rolling "last N days" window. Supervisors also hand out assignments tied to a calendar period: "fly 1 hour in October", "fly each aircraft type for 15 minutes this quarter". These change from month to month and unit to unit, so they must be fully configurable from Settings without a release.

Separately, the currency rule form takes the vehicle model as free text. A typo silently makes a rule match no flights. Models should be picked from the fleet instead.

## Goals

- A new **Flight Requirements** feature for fixed-period assignments, separate from currency.
- Requirements can use a calendar month, quarter or year, a fiscal quarter or year, a custom date range, or every N months from a start date.
- Requirements can be one-time or recurring.
- Targets can be hours and minutes, a number of flights, or both.
- Aircraft scope is chosen by toggling the models in the fleet, with the option to require the target on each model separately.
- Every past period's result per pilot is kept as history.
- The free-text vehicle model field on currency rules is replaced by the same fleet model toggles.

## Non-goals

- Changing how currency is evaluated (rolling window, expiry date, reminders).
- Training hours, certification tracking, or non-flight tasks.
- Per-tenant data separation.

## Anti-goals

The work has failed if any of these is true:

- Editing a requirement rewrites the result of a period that has already closed.
- A requirement silently matches no flights because of a model spelling difference.
- Requirements change the currency compliance percentage or send reminders without the admin turning that on.
- A flight that is not reviewed counts toward a requirement. The same `counted_flights_filter()` applies as for currency.

## Currency vs. requirements

| | Currency (existing) | Flight Requirements (new) |
|---|---|---|
| Question | Is the pilot legal to fly right now? | Did the pilot meet this period's assignment? |
| Window | Rolling, last N days | Fixed calendar or custom period |
| Status | Current, Lapsed, Expires on | On track, Met, Missed, Excused |
| History | None | One saved result per pilot per period |
| Compliance % and reminders | Yes | Only when turned on for the requirement |

## Fleet model picker

Shared by the currency rule form and the requirement form.

### Source of the list

- A new endpoint, `GET /api/currency/models`, returns the distinct vehicle models in the fleet with a count of aircraft for each. It is guarded by `certifications.view`. It does not depend on `fleet.view`, so anyone who can manage rules can see the list.
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
| Period | Calendar month, calendar quarter, calendar year, fiscal quarter, fiscal year, custom date range, every N months from a start date |
| Repeats | One time, or recurring with an optional end date |
| Starts | The first period (for example, October 2026 or Q4 2026) |
| Target | Hours and minutes, flights, or both |
| Aircraft | Fleet model picker, with Combined or Each separately |
| Applies to | All active pilots, or selected pilots |
| Counts toward compliance | Off by default. When on, it feeds the compliance percentage and reminders |
| Active | On or off |

The fiscal year start month is a unit setting, defaulting to October.

The form shows a live plain-English summary, for example:

> Every **quarter**, **all active pilots** must fly **15 min** on **each of: X10, X2E, LEMUR 2**, starting **Q4 2026**, no end date.

### Examples

| Assignment | Period | Repeats | Target | Aircraft |
|---|---|---|---|---|
| Fly 1 hour in October | Calendar month, Oct 2026 | One time | 1h | All aircraft |
| Fly 1 hour in the next 3 months | Custom range, today to 3 months out | One time | 1h | All aircraft |
| Fly each drone type 15 minutes per quarter | Calendar quarter, from Q4 2026 | Recurring | 15m | All active models, each separately |

## Evaluation

- One pure function returns the period that contains a given date, `(start, end)` inclusive, for a requirement. It holds all calendar math and is tested on its own: month lengths, leap years, quarter and fiscal boundaries, and custom ranges.
- Flight dates are already local dates (migration 0008), so period boundaries use `Flight.date` directly.
- A pilot's status in the current period:
  - **Met**: the target is reached (on every model, when "each separately").
  - **On track**: not met yet, and the period is still open.
  - **Missed**: the period closed without meeting the target.
  - **Excused**: a supervisor excused the pilot for this period (leave, injury, new hire).
- A pilot added partway through a period is excused for that period automatically. The supervisor can remove the excusal.

## History

- When a period closes, each assigned pilot's result is saved: the hours and flights per model, the status, and a copy of the requirement's target and scope at that time.
- Saving happens when a closed period is first read, and also from the existing daily scheduler. Both are safe to run twice.
- Edits to a requirement apply to the current period and later ones. Saved periods are never recalculated.
- Re-reviewing an old flight does not change a saved period. An admin can recalculate one period on purpose, and that is audited.

## Screens

- **Settings, Flight Requirements**: a list of requirements and the builder form above. It sits next to Currency Rules and uses the same `certifications.manage` permission.
- **Dashboard, This Period card**: for each active requirement, the days left in the period, how many pilots have met it, and each pilot's progress, for example "X10 12/15m, X2E done".
- **Pilot detail, Requirements tab**: the current period's progress and a history table of past periods.
- **Settings, Currency Rules form**: the free-text model field is replaced by the fleet model picker.

## Data model

- `flight_requirements`: definition (name, description, period type, period parameters, repeats, start, end, target hours, target flights, model mode, counts toward compliance, active, timestamps, created and modified by).
- `flight_requirement_models`: requirement id and model name. No rows means all aircraft.
- `flight_requirement_pilots`: requirement id and pilot id. No rows means all active pilots.
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

- Period math: every period type, around month, quarter, fiscal and year boundaries, February in leap and non-leap years.
- Model matching ignores case, and "each separately" fails when any one model is short.
- Only reviewed flights count.
- Closed periods do not change after a requirement is edited or a flight is re-reviewed.
- Requirements with compliance off do not change the dashboard compliance percentage or reminders.
- The currency migration keeps each existing rule's behavior exactly as before.
- Permission coverage tests include every new route.

## Open questions

1. Does one installation serve more than one agency, or does "agency to agency" mean units or squads within one agency? If either, add pilot groups so a requirement can target a group.
2. The example "fly 1 hour in the next 3 hours" is read here as 3 months. Confirm, or correct it to the intended span.
