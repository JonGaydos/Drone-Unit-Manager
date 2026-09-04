/**
 * Shared organization default location helpers.
 *
 * The org default is stored in three public settings keys
 * (org_default_lat / org_default_lon / org_location_name). When unset or
 * unparseable, everything falls back to the White House so Weather, the
 * Airspace map, and the dashboard weather tile always have a sensible center.
 */

export const DEFAULT_ORG_LOCATION = { lat: 38.8977, lon: -77.0365, name: 'White House, Washington D.C.' }

/**
 * Resolve the org default location from a GET /settings response.
 * @param {Array<{key: string, value: string}>} settings - settings rows.
 * @returns {{lat: number, lon: number, name: string}}
 */
export function resolveOrgLocation(settings) {
  const find = (k) => settings?.find(s => s.key === k)?.value
  const lat = Number.parseFloat(find('org_default_lat'))
  const lon = Number.parseFloat(find('org_default_lon'))
  const name = find('org_location_name')
  if (Number.isFinite(lat) && Number.isFinite(lon)) return { lat, lon, name: name || `${lat}, ${lon}` }
  return { ...DEFAULT_ORG_LOCATION }
}
