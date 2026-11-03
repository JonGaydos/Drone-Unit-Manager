// The default grid from docs/specs/2026-11-02-role-permissions-design.md, one
// row per key: [key, supervisor, pilot, viewer]. Admin holds every key at its
// highest value, as the backend resolves it.
const GRID = [
  ['flights.view', 'yes', 'yes', 'yes'],
  ['flights.create', 'yes', 'yes', 'no'],
  ['flights.edit', 'all', 'own', 'none'],
  ['flights.delete', 'all', 'none', 'none'],
  ['flights.review', 'yes', 'no', 'no'],
  ['flight_plans.view', 'yes', 'yes', 'yes'],
  ['flight_plans.create', 'yes', 'yes', 'no'],
  ['flight_plans.edit', 'all', 'own', 'none'],
  ['flight_plans.approve', 'yes', 'no', 'no'],
  ['incidents.view', 'yes', 'yes', 'yes'],
  ['incidents.create', 'yes', 'yes', 'no'],
  ['incidents.edit', 'all', 'own', 'none'],
  ['incidents.resolve', 'yes', 'no', 'no'],
  ['incidents.delete', 'yes', 'no', 'no'],
  ['logs.view', 'yes', 'yes', 'yes'],
  ['logs.create', 'yes', 'yes', 'no'],
  ['logs.edit', 'all', 'own', 'none'],
  ['maintenance.view', 'yes', 'yes', 'yes'],
  ['maintenance.create', 'yes', 'yes', 'no'],
  ['maintenance.edit', 'all', 'own', 'none'],
  ['schedules.complete', 'yes', 'yes', 'no'],
  ['schedules.manage', 'yes', 'no', 'no'],
  ['fleet.view', 'yes', 'yes', 'yes'],
  ['fleet.manage', 'yes', 'no', 'no'],
  ['fleet.location', 'yes', 'yes', 'no'],
  ['checkouts.use', 'yes', 'yes', 'no'],
  ['checkouts.delete', 'yes', 'no', 'no'],
  ['pilots.view', 'yes', 'yes', 'yes'],
  ['pilots.contacts', 'yes', 'yes', 'no'],
  ['pilots.edit', 'all', 'own', 'none'],
  ['pilots.manage', 'yes', 'no', 'no'],
  ['certifications.view', 'yes', 'yes', 'yes'],
  ['certifications.manage', 'yes', 'no', 'no'],
  ['checklists.view', 'yes', 'yes', 'yes'],
  ['checklists.complete', 'yes', 'yes', 'no'],
  ['checklists.manage', 'yes', 'no', 'no'],
  ['calendar.view', 'yes', 'yes', 'yes'],
  ['calendar.create', 'yes', 'yes', 'no'],
  ['calendar.edit', 'all', 'own', 'none'],
  ['files.view', 'yes', 'yes', 'yes'],
  ['files.upload', 'all', 'own', 'none'],
  ['files.edit', 'all', 'own', 'none'],
  ['files.custody', 'yes', 'no', 'no'],
  ['folders.manage', 'yes', 'no', 'no'],
  ['alerts.view', 'yes', 'yes', 'yes'],
  ['alerts.dismiss', 'yes', 'no', 'no'],
  ['reports.generate', 'yes', 'yes', 'no'],
  ['reports.export', 'yes', 'yes', 'yes'],
  ['authority.view', 'yes', 'yes', 'yes'],
  ['authority.manage', 'yes', 'no', 'no'],
  ['registrations.view', 'yes', 'yes', 'yes'],
  ['registrations.manage', 'no', 'no', 'no'],
  ['audit.view', 'no', 'no', 'no'],
  ['digest.redirect', 'yes', 'no', 'no'],
]

const LEVEL_VALUES = new Set(['none', 'own', 'all'])

function column(index) {
  return Object.fromEntries(GRID.map(row => [row[0], row[index]]))
}

export const DEFAULT_PERMISSIONS = {
  admin: Object.fromEntries(GRID.map(([key, sup]) => [key, LEVEL_VALUES.has(sup) ? 'all' : 'yes'])),
  supervisor: column(1),
  pilot: column(2),
  viewer: column(3),
}

/** A user as /auth/me returns it: the role's default grid, then any overrides.
 *  A user that already carries a permissions map keeps it. */
export function withPermissions(user, overrides = {}) {
  return { ...user, permissions: { ...(user.permissions || DEFAULT_PERMISSIONS[user.role] || {}), ...overrides } }
}
