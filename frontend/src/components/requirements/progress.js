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
  current: 'Current',
  lapsed: 'Lapsed',
  not_yet_due: 'Not yet due',
}

// The date beside a rolling status: when a current pilot would lapse, since
// when a lapsed one has been lapsed, until when an excusal lasts and from
// when a pilot not yet due can lapse.
const ROLLING_DATES = {
  current: (row) => row.lapse_date && `lapses on ${formatDate(row.lapse_date)}`,
  lapsed: (row, since) => since && `since ${formatDate(since)}`,
  excused: (row) => row.excused_until && `until ${formatDate(row.excused_until)}`,
  not_yet_due: (row) => row.due_on && `due from ${formatDate(row.due_on)}`,
}

/** "lapses on Dec 3, 2026", "since Nov 2, 2026" (with `since`, the open lapse's
 *  start), "until Jan 31, 2027", or "" when there is no date to give. */
export function rollingDateText(row, since = null) {
  return ROLLING_DATES[row.status]?.(row, since) || ''
}

/** "3 current, 1 lapsed" for a rolling window's pilots. */
export function rollingCounts(pilots) {
  const count = status => pilots.filter(p => p.status === status).length
  return `${count('current')} current, ${count('lapsed')} lapsed`
}

/** The start of each pilot's open lapse on a requirement, by pilot id, from /requirements/flags. */
export function lapseStarts(flags, requirementId) {
  const starts = {}
  for (const [pilotId, list] of Object.entries(flags || {})) {
    const lapse = list.find(f => f.kind === 'lapsed' && f.requirement_id === requirementId)
    if (lapse) starts[pilotId] = lapse.period_start
  }
  return starts
}

/** "1 flight", "3 flights". */
export function countText(count, word) {
  return `${count} ${word}${count === 1 ? '' : 's'}`
}

/** "12m", "1h", "1h 25m". Partial minutes are dropped, so an unmet target never reads as met. */
export function durationText(minutes) {
  const whole = Math.floor(minutes)
  const hours = Math.floor(whole / 60)
  const rest = whole % 60
  if (hours === 0) return `${rest}m`
  return rest ? `${hours}h ${rest}m` : `${hours}h`
}

function amountText(total, target) {
  const parts = []
  if (target.target_minutes != null) parts.push(`${durationText(total.minutes)}/${durationText(target.target_minutes)}`)
  if (target.target_flights != null) parts.push(`${total.flights}/${target.target_flights} flights`)
  // With the target unknown, the plain amounts.
  return parts.join(' ') || `${durationText(total.minutes)} ${countText(total.flights, 'flight')}`
}

/**
 * "X10 12m/15m, X2E done": each model's amount against the target, or "done"
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

/**
 * Which excusal action a row offers: un-excuse an excused one, excuse one not
 * met, and nothing on a row saved while the requirement was switched off.
 */
export function excuseAction(row) {
  if (row.switched_off) return null
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
