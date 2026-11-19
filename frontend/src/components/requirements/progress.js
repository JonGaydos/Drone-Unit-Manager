/**
 * Plain text for flight requirement progress: per-model amounts against the
 * target, excusal labels and period wording, shared by the dashboard tile,
 * the pilot card and the pilots list.
 */
import { formatDate } from '@/lib/utils'

/** Totals key for all aircraft, or the combined models. */
const ALL_KEY = '*'

export const STATUS_LABELS = {
  met: 'Met',
  on_track: 'On track',
  pending_review: 'Pending review',
  missed: 'Missed',
  excused: 'Excused',
}

/** "1 flight", "3 flights". */
export function countText(count, word) {
  return `${count} ${word}${count === 1 ? '' : 's'}`
}

function amountText(total, target) {
  const parts = []
  if (target.target_minutes != null) parts.push(`${Math.floor(total.minutes)}/${target.target_minutes}m`)
  if (target.target_flights != null) parts.push(`${total.flights}/${target.target_flights} flights`)
  // With the target unknown, the plain amounts.
  return parts.join(' ') || `${Math.floor(total.minutes)}m ${countText(total.flights, 'flight')}`
}

/**
 * "X10 12/15m, X2E done": each model's amount against the target, or "done"
 * once `metByModel` says it is met. All aircraft and combined models carry no
 * model name. Without `metByModel`, amounts are always shown.
 */
export function progressText(totals, metByModel, target) {
  const entries = Object.entries(totals || {})
  if (entries.length === 0) return 'Nothing flown yet'
  return entries.map(([key, total]) => {
    const amount = metByModel?.[key] ? 'done' : amountText(total, target)
    return key === ALL_KEY ? amount : `${key} ${amount}`
  }).join(', ')
}

/**
 * "Excused automatically: <reason>" for an excusal nobody made (no
 * `excused_by_id`), "Excused: <reason>" for one a supervisor made, and "" for
 * a row that is not excused. Rows that do not say who excused them read as a
 * plain excusal.
 */
export function excusalText(row) {
  if (!row.excused) return ''
  const automatic = 'excused_by_id' in row && row.excused_by_id == null
  const label = automatic ? 'Excused automatically' : 'Excused'
  return row.excused_reason ? `${label}: ${row.excused_reason}` : label
}

/** Which excusal action a row offers: un-excuse an excused one, excuse one not met. */
export function excuseAction(row) {
  if (row.excused) return 'unexcuse'
  return row.status === 'met' ? null : 'excuse'
}

/** "12 days left", "Last day" or "Ended". */
export function daysLeftText(days) {
  if (days <= 0) return 'Ended'
  if (days === 1) return 'Last day'
  return `${days} days left`
}

export function metCount(pilots) {
  return pilots.filter(p => p.status === 'met').length
}

/** "Nov 1, 2026 to Nov 30, 2026". */
export function periodText(start, end) {
  return `${formatDate(start)} to ${formatDate(end)}`
}
