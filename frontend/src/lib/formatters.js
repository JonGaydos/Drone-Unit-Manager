/**
 * Shared sorting and formatting utilities
 */

export function sortByName(items, nameKey = 'full_name') {
  return [...items].sort((a, b) =>
    (a[nameKey] || '').localeCompare(b[nameKey] || '')
  )
}

export function sortPilots(pilots) {
  return sortByName(pilots, 'full_name')
}

export function sortVehicles(vehicles) {
  return [...vehicles].sort((a, b) =>
    `${a.manufacturer} ${a.model}`.localeCompare(`${b.manufacturer} ${b.model}`)
  )
}

export function sortByField(items, field = 'name') {
  return [...items].sort((a, b) =>
    (a[field] || '').localeCompare(b[field] || '')
  )
}

export function formatStatusText(status) {
  if (!status) return ''
  return status.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
}
