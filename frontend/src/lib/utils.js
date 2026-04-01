/**
 * General-purpose utility functions for class merging, unit conversion, and date formatting.
 */
import { clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

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
 * Format an ISO datetime string to a localized date and time (e.g. "Mar 26, 2026, 3:45 PM").
 * @param {string} iso - ISO 8601 datetime string.
 * @returns {string} Formatted datetime or em-dash if invalid/empty.
 */
export function formatDateTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' })
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
  const match = value.match(/^00(\d{2})-/)
  if (match) {
    const yr = Number.parseInt(match[1], 10)
    const century = yr >= 50 ? '19' : '20'
    return value.replace(/^00\d{2}/, century + match[1])
  }
  return value
}
