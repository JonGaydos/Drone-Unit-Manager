# Fleet lifecycle dates and Other equipment

Date: 2026-07-13
Status: approved

## Goal

Track every fleet item through its full service life with uniform fields:
one acquired date and one decommissioned date across all fleet types, plus a
new "Other" equipment type for miscellaneous items (cases, tablets, bags,
cables) with the same capabilities batteries have today (maintenance,
documents, checkouts).

## Current state

- `vehicles.acquired_date` and `batteries.purchase_date` are the only
  acquisition dates; controllers, docks, sensor_packages, and attachments
  have none.
- No decommissioned date anywhere; all six types have a `status` string
  (active / retired / damaged / maintenance).
- Maintenance allows entity_type "other" but with no backing table (label
  only, no item picker). Documents and equipment checkouts do not accept
  "other".

## Design

### 1. Uniform dates

- `acquired_date` is the canonical field. Alembic migration renames
  `batteries.purchase_date` to `batteries.acquired_date` (SQLite: batch
  alter, data preserved) and adds nullable `acquired_date` to controllers,
  docks, sensor_packages, and attachments.
- New nullable `decommissioned_date` on vehicles, batteries, controllers,
  docks, sensor_packages, attachments, and the new other_equipment table.
- Auto-fill: on any update that changes status to `retired` or `damaged`
  while `decommissioned_date` is empty, the backend sets it to today.
  The date remains editable and clearable; reactivating an item never
  clears it automatically.
- API: `purchase_date` is renamed to `acquired_date` in battery schemas
  (breaking change for external readers). All fleet type schemas gain
  `acquired_date` and `decommissioned_date`.
- Backup restore accepts legacy `purchase_date` keys in battery rows and
  maps them to `acquired_date`, so old backup archives still import.
- battery_dedupe `_fill_missing_fields` follows the rename.
- UI: every Fleet tab shows Acquired and Decommissioned columns and form
  fields; detail pages show both; "Purchase" wording becomes "Acquired".

### 2. Other equipment

- New table `other_equipment`: id, name (required), category (free text),
  serial_number (optional), status (default active), acquired_date,
  decommissioned_date, notes, created_at, updated_at.
- CRUD endpoints in the equipment router following the existing per-type
  pattern (`/api/other-equipment`), admin-gated writes like other types.
- Fleet page gains an "Other" tab (columns: name, category, serial,
  status, acquired, decommissioned) with the standard add/edit/delete
  modals, plus a detail page following the AttachmentDetailPage pattern.
- Maintenance: ENTITY_MODELS maps "other" to OtherEquipment. New records
  and schedules pick a specific item (active-only, per existing picker
  rules) and resolve its name. Legacy "other" rows without entity_id stay
  valid and render as they do today; validation continues to accept a
  null entity_id for "other" so legacy records can still be edited.
- Documents and equipment checkouts accept entity_type "other".
- Backup: other_equipment joins EXPORT_ORDER (tier 2).

### 3. Out of scope

- No provider sync for other equipment (manual only), no merge tooling for
  it, no status workflow changes beyond the auto-fill, no changes to the
  organization-wide maintenance type.

## Testing

- Backend: migration produces the new columns; battery API round-trips
  acquired_date; auto-fill sets decommissioned_date on retire and respects
  an existing value; other-equipment CRUD; maintenance validation for
  "other" with and without entity_id; checkout/document acceptance;
  backup restore of a legacy purchase_date row.
- Frontend: FleetPage Other tab renders and submits; renamed battery
  field; detail page date fields; maintenance modal offers Other items.
