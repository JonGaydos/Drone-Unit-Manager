/**
 * Shared sorting and formatting utilities for lists of pilots, vehicles, and equipment.
 */

/**
 * Sort an array of objects alphabetically by a name field.
 * @param {Array<Object>} items - Items to sort.
 * @param {string} [nameKey='full_name'] - Object key to sort by.
 * @returns {Array<Object>} New sorted array (does not mutate the original).
 */
export function sortByName(items, nameKey = 'full_name') {
  return [...items].sort((a, b) =>
    (a[nameKey] || '').localeCompare(b[nameKey] || '')
  )
}

/**
 * Sort pilots alphabetically by full name.
 * @param {Array<Object>} pilots - Pilot objects with full_name field.
 * @returns {Array<Object>} Sorted pilot array.
 */
export function sortPilots(pilots) {
  return sortByName(pilots, 'full_name')
}

/**
 * Sort vehicles alphabetically by "manufacturer model" string.
 * @param {Array<Object>} vehicles - Vehicle objects with manufacturer and model fields.
 * @returns {Array<Object>} Sorted vehicle array.
 */
export function sortVehicles(vehicles) {
  return [...vehicles].sort((a, b) =>
    `${a.manufacturer} ${a.model}`.localeCompare(`${b.manufacturer} ${b.model}`)
  )
}

/**
 * Sort an array of objects alphabetically by a specified field.
 * @param {Array<Object>} items - Items to sort.
 * @param {string} [field='name'] - Object key to sort by.
 * @returns {Array<Object>} Sorted array.
 */
export function sortByField(items, field = 'name') {
  return [...items].sort((a, b) =>
    (a[field] || '').localeCompare(b[field] || '')
  )
}

/**
 * Sort pilots with active status first, then alphabetically by first name.
 * @param {Array<Object>} pilots - Pilot objects with status and first_name fields.
 * @returns {Array<Object>} Sorted pilot array.
 */
export function sortPilotsActiveFirst(pilots) {
  return [...pilots].sort((a, b) => {
    if (a.status !== b.status) return a.status === 'active' ? -1 : 1
    return (a.first_name || '').localeCompare(b.first_name || '')
  })
}

/**
 * Generate a human-readable display name for a vehicle.
 * Falls back through nickname, manufacturer+model, serial number, then "Unknown".
 * @param {Object} v - Vehicle object.
 * @returns {string} Display name.
 */
export function vehicleDisplayName(v) {
  return v.nickname || `${v.manufacturer || ''} ${v.model || ''}`.trim() || v.serial_number || 'Unknown'
}

/**
 * Generate a human-readable display name for an equipment item.
 * Falls back through nickname, serial number, manufacturer+model, then "Unknown".
 * @param {Object} item - Equipment object.
 * @returns {string} Display name.
 */
export function equipmentDisplayName(item) {
  return item.nickname || item.serial_number || `${item.manufacturer || ''} ${item.model || ''}`.trim() || 'Unknown'
}

/**
 * Convert a snake_case status string to Title Case for display.
 * @param {string} status - Status value (e.g. "in_progress").
 * @returns {string} Formatted string (e.g. "In Progress").
 */
export function formatStatusText(status) {
  if (!status) return ''
  return status.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
}
