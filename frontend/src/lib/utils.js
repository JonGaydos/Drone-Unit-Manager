/**
 * General-purpose utility functions for class merging, unit conversion, and date formatting.
 */
import { clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

// Program-wide display timezone (IANA name). null = use the browser's local zone.
let _displayTimezone = null

/** Set the program-wide display timezone (IANA name), e.g. 'America/Chicago'. */
export function setDisplayTimezone(tz) { _displayTimezone = tz || null }

/** Get the configured display timezone, or undefined to fall back to browser-local. */
export function getDisplayTimezone() { return _displayTimezone || undefined }

/**
 * Run `fn` with `tz`; if an invalid IANA zone name makes it throw (RangeError),
 * retry with no timezone (browser-local) instead of crashing.
 * @param {string|undefined} tz - IANA zone to try first.
 * @param {(tz: string|undefined) => T} fn - Callback that receives a timeZone value.
 * @returns {T} The callback's result, from the zoned attempt or the local fallback.
 */
function withZoneFallback(tz, fn) {
  try {
    return fn(tz)
  } catch {
    return fn(undefined)
  }
}

/** Curated IANA timezones offered in the setup and settings dropdowns. */
export const TIMEZONES = [
  'America/New_York', 'America/Chicago', 'America/Denver', 'America/Phoenix',
  'America/Los_Angeles', 'America/Anchorage', 'Pacific/Honolulu',
  'UTC', 'Europe/London', 'Europe/Paris', 'Australia/Sydney',
]

/**
 * Merge Tailwind CSS class names with conflict resolution.
 * Combines clsx conditional logic with tailwind-merge deduplication.
 * @param {...(string|Object|Array)} inputs - Class values, objects, or arrays.
 * @returns {string} Merged class string.
 */
export function cn(...inputs) {
  return twMerge(clsx(inputs))
}

/**
 * Format a duration in seconds to a human-readable string.
 * @param {number} seconds - Duration in seconds.
 * @returns {string} Formatted string like "2h 15m" or "5m 30s", or em-dash if falsy.
 */
export function formatDuration(seconds) {
  if (!seconds) return '—'
  const hrs = Math.floor(seconds / 3600)
  const mins = Math.floor((seconds % 3600) / 60)
  const secs = seconds % 60
  if (hrs > 0) return `${hrs}h ${mins}m`
  return `${mins}m ${secs}s`
}

/**
 * Convert seconds to decimal hours with one decimal place.
 * @param {number} seconds - Duration in seconds.
 * @returns {string} Hours as a fixed-point string (e.g. "2.5").
 */
export function formatHours(seconds) {
  if (!seconds) return '0.0'
  return (seconds / 3600).toFixed(1)
}

/**
 * Convert meters to feet, rounded to the nearest integer.
 * @param {number|null} m - Distance in meters.
 * @returns {number|null} Distance in feet, or null if input is null/undefined.
 */
export function metersToFeet(m) {
  if (m == null) return null
  return Math.round(m * 3.28084)
}

/**
 * Convert meters per second to miles per hour, rounded to one decimal.
 * @param {number|null} mps - Speed in meters per second.
 * @returns {number|null} Speed in mph, or null if input is null/undefined.
 */
export function mpsToMph(mps) {
  if (mps == null) return null
  return Math.round(mps * 2.23694 * 10) / 10
}

/**
 * Format an ISO date string to a localized short date (e.g. "Mar 26, 2026").
 * Handles date-only strings by appending T00:00:00 to avoid timezone shifts.
 * @param {string} iso - ISO 8601 date or datetime string.
 * @returns {string} Formatted date or em-dash if invalid/empty.
 */
export function formatDate(iso) {
  if (!iso) return '—'
  const d = new Date(iso.includes('T') ? iso : iso + 'T00:00:00')
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

/**
 * Compute the whole-day delta from local midnight today to a date-only string.
 * Parses date-only strings as LOCAL midnight (appends T00:00:00 like formatDate)
 * to avoid UTC-parsing off-by-one errors in US timezones.
 * @param {string} iso - ISO 8601 date or datetime string.
 * @returns {number|null} Whole-day delta (negative if past), or null if empty/invalid.
 */
export function daysUntil(iso) {
  if (!iso) return null
  const d = new Date(iso.includes('T') ? iso : iso + 'T00:00:00')
  if (Number.isNaN(d.getTime())) return null
  const target = new Date(d.getFullYear(), d.getMonth(), d.getDate())
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return Math.round((target - today) / 86400000)
}

/**
 * Format an ISO datetime string to a localized date and time (e.g. "Mar 26, 2026, 3:45 PM").
 * Expects a `Z`-suffixed (UTC) ISO string for flight times; a naive (offset-less)
 * datetime is parsed as browser-local and then rendered in the configured zone,
 * which double-shifts if the two differ.
 * @param {string} iso - ISO 8601 datetime string.
 * @returns {string} Formatted datetime or em-dash if invalid/empty.
 */
export function formatDateTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return withZoneFallback(getDisplayTimezone(), tz =>
    d.toLocaleString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit', timeZone: tz }))
}

/**
 * Fix two-digit year prefixes in date input values (e.g. "0026-12-12" -> "2026-12-12").
 * Assumes years 00-49 are 2000s and 50-99 are 1900s.
 * @param {string} value - Date string from an input element.
 * @returns {string} Corrected date string, or the original value if no fix needed.
 */
export function normalizeDateValue(value) {
  if (!value) return value
  // Handle dates like "0026-12-12" → "2026-12-12"
  const match = /^00(\d{2})-/.exec(value)
  if (match) {
    const yr = Number.parseInt(match[1], 10)
    const century = yr >= 50 ? '19' : '20'
    return value.replace(/^00\d{2}/, century + match[1])
  }
  return value
}

/**
 * Format an ISO datetime to a localized time-of-day in the configured zone.
 * @param {string} iso - ISO 8601 datetime string (UTC `Z` for flight times).
 * @returns {string} e.g. "11:26 AM", or em-dash if invalid/empty.
 */
export function formatTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return withZoneFallback(getDisplayTimezone(), tz =>
    d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', timeZone: tz }))
}

/**
 * Convert a UTC ISO instant to a 'YYYY-MM-DDTHH:mm' wall value in `tz`,
 * suitable for a datetime-local input.
 * @param {string} iso - UTC ISO 8601 string.
 * @param {string} [tz] - IANA zone; defaults to the configured display zone.
 * @returns {string} datetime-local value, or '' if invalid/empty.
 */
export function utcIsoToZonedInput(iso, tz = getDisplayTimezone()) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return withZoneFallback(tz, zone => {
    const parts = new Intl.DateTimeFormat('en-CA', {
      timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', hour12: false,
    }).formatToParts(d)
    const g = t => parts.find(p => p.type === t).value
    let hh = g('hour'); if (hh === '24') hh = '00'
    return `${g('year')}-${g('month')}-${g('day')}T${hh}:${g('minute')}`
  })
}

/**
 * Convert a 'YYYY-MM-DDTHH:mm' wall value (interpreted in `tz`) to a UTC ISO
 * instant ending in 'Z'.
 * @param {string} wall - datetime-local value.
 * @param {string} [tz] - IANA zone; defaults to the configured display zone.
 * @returns {string|null} UTC ISO string, or null if empty.
 */
export function zonedInputToUtcIso(wall, tz = getDisplayTimezone()) {
  if (!wall) return null
  const toLocal = () => {
    const d = new Date(wall)
    return Number.isNaN(d.getTime()) ? null : d.toISOString().replace('.000Z', 'Z')
  }
  if (!tz) return toLocal()
  try {
    const [datePart, timePart] = wall.split('T')
    const [y, mo, d] = datePart.split('-').map(Number)
    const [h, mi] = timePart.split(':').map(Number)
    const asUTC = Date.UTC(y, mo - 1, d, h, mi)
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
    }).formatToParts(new Date(asUTC))
    const gp = t => Number(parts.find(p => p.type === t).value)
    let hh = gp('hour'); if (hh === 24) hh = 0
    const shown = Date.UTC(gp('year'), gp('month') - 1, gp('day'), hh, gp('minute'), gp('second'))
    const offset = shown - asUTC
    return new Date(asUTC - offset).toISOString().replace('.000Z', 'Z')
  } catch {
    // Invalid IANA zone name (e.g. from a raw API write bypassing the UI dropdowns).
    return toLocal()
  }
}
