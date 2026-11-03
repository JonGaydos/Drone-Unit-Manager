/** Pure helpers for the role permissions grid. */

export const ADMIN = 'admin'
export const EDITABLE_ROLES = ['supervisor', 'pilot', 'viewer']
export const ROLES = [ADMIN, ...EDITABLE_ROLES]
export const ROLE_LABELS = { admin: 'Admin', supervisor: 'Supervisor', pilot: 'Pilot', viewer: 'Viewer' }

export const VALUE_LABELS = { yes: 'Yes', no: 'No', none: 'None', own: 'Own', all: 'All' }
export const OPTIONS = { bool: ['no', 'yes'], level: ['none', 'own', 'all'] }

const lowest = (def) => OPTIONS[def.kind][0]

/** Registry rows grouped by feature, in registry order. */
export function groupByFeature(registry) {
  const groups = new Map()
  for (const def of registry) {
    if (!groups.has(def.feature)) groups.set(def.feature, { feature: def.feature, rows: [] })
    groups.get(def.feature).rows.push(def)
  }
  return [...groups.values()]
}

/**
 * A copy of the grid with one cell set. Turning a view off also sets every key
 * that requires it, in any feature, to its lowest value for that role. Turning
 * it back on restores nothing.
 */
export function setCell(values, registry, role, key, value) {
  const target = registry.find(def => def.key === key)
  const roleValues = { ...values[role], [key]: value }
  if (target && value === lowest(target)) {
    for (const def of registry) {
      if (def.requires === key) roleValues[def.key] = lowest(def)
    }
  }
  return { ...values, [role]: roleValues }
}

/** Whether a cell can be edited, and the short reason when it cannot. */
export function cellState(def, role, values, registry) {
  if (role === ADMIN) return { disabled: true, reason: 'Always on' }
  if (role === 'viewer' && def.viewer_locked) return { disabled: true, reason: 'Viewers are read only' }
  if (def.requires && values[role][def.requires] === 'no') {
    const view = registry.find(other => other.key === def.requires)
    return { disabled: true, reason: `Needs ${view.feature} view on` }
  }
  return { disabled: false, reason: null }
}

/** The changed cells to send: editable roles only, never a locked viewer cell. */
export function diffChanges(saved, draft, registry) {
  const changes = []
  for (const role of EDITABLE_ROLES) {
    for (const def of registry) {
      if (role === 'viewer' && def.viewer_locked) continue
      const value = draft[role][def.key]
      if (value !== saved[role][def.key]) changes.push({ role, key: def.key, value })
    }
  }
  return changes
}
