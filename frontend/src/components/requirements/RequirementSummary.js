/**
 * Plain-English text for a flight requirement: the live summary under the
 * builder form, and the short period and target labels of the list.
 */
import { formatDate } from '@/lib/utils'
import { targetMinutesOf } from './formState'

export const PERIOD_LABELS = {
  calendar_month: 'Calendar month',
  calendar_quarter: 'Calendar quarter',
  calendar_year: 'Calendar year',
  fiscal_quarter: 'Fiscal quarter',
  fiscal_year: 'Fiscal year',
  monthly_window: 'Monthly window',
  span: 'Span from a start date',
  custom: 'Custom date range',
  every_n_months: 'Every N months',
  rolling: 'Rolling window',
}

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
  'September', 'October', 'November', 'December']

// Calendar and fiscal periods are named after the period holding the start date.
const NAMED_PERIODS = new Set(['calendar_month', 'calendar_quarter', 'calendar_year', 'fiscal_quarter', 'fiscal_year'])

const RECURRING_PHRASES = {
  calendar_month: 'Every month',
  calendar_quarter: 'Every quarter',
  calendar_year: 'Every year',
  fiscal_quarter: 'Every fiscal quarter',
  fiscal_year: 'Every fiscal year',
}

const NO_START = '(no start date yet)'

function plural(count, word) {
  return count === 1 ? `1 ${word}` : `${count} ${word}s`
}

function toNumber(value) {
  const n = Number.parseInt(value, 10)
  return Number.isNaN(n) ? null : n
}

function capitalize(text) {
  return text.charAt(0).toUpperCase() + text.slice(1)
}

function ordinal(day) {
  const tens = day % 100
  if (tens >= 11 && tens <= 13) return `${day}th`
  const suffix = { 1: 'st', 2: 'nd', 3: 'rd' }[day % 10] || 'th'
  return day + suffix
}

/** "a", "a or b", "a, b or c" with the given last joining word. */
function joinList(items, word) {
  if (items.length <= 1) return items.join('')
  return `${items.slice(0, -1).join(', ')} ${word} ${items.at(-1)}`
}

function clockText(hhmm) {
  if (!hhmm) return '?'
  const [h, m] = hhmm.split(':').map(Number)
  const suffix = h < 12 ? 'AM' : 'PM'
  return `${h % 12 || 12}:${String(m).padStart(2, '0')} ${suffix}`
}

function fiscalParts(year, month, fiscalStartMonth) {
  const fiscalYear = fiscalStartMonth > 1 && month >= fiscalStartMonth ? year + 1 : year
  const quarter = Math.floor(((month - fiscalStartMonth + 12) % 12) / 3) + 1
  return { fiscalYear, quarter }
}

/**
 * The first period's name: "October 2026", "Q4 2026", "2026", "Q1 FY2027",
 * "FY2027", or the start date for the other period types.
 */
export function startLabel(form, fiscalStartMonth) {
  if (!form.start_date) return NO_START
  const [year, month] = form.start_date.split('-').map(Number)
  const { fiscalYear, quarter } = fiscalParts(year, month, fiscalStartMonth)
  switch (form.period_type) {
    case 'calendar_month': return `${MONTHS[month - 1]} ${year}`
    case 'calendar_quarter': return `Q${Math.floor((month - 1) / 3) + 1} ${year}`
    case 'calendar_year': return String(year)
    case 'fiscal_quarter': return `Q${quarter} FY${fiscalYear}`
    case 'fiscal_year': return `FY${fiscalYear}`
    default: return formatDate(form.start_date)
  }
}

function windowRange(form) {
  const first = toNumber(form.window_start_day)
  const last = toNumber(form.window_end_day)
  if (first === null || last === null) return 'in a window of days not yet set'
  const tail = last < first ? ' of the following month' : ''
  return `from the ${ordinal(first)} to the ${ordinal(last)}${tail}`
}

function spanUnit(form) {
  return (form.span_unit || 'days').slice(0, -1)
}

function everyPhrase(count, word) {
  return count === 1 ? `Every ${word}` : `Every ${plural(count, word)}`
}

function recurringPhrase(form) {
  switch (form.period_type) {
    case 'monthly_window': return `Every month ${windowRange(form)}`
    case 'span': return everyPhrase(toNumber(form.span_length) ?? 1, spanUnit(form))
    case 'every_n_months': return everyPhrase(toNumber(form.every_months) ?? 1, 'month')
    default: return RECURRING_PHRASES[form.period_type]
  }
}

function oneTimePhrase(form, fiscalStartMonth) {
  switch (form.period_type) {
    case 'monthly_window': return capitalize(windowRange(form))
    case 'span': return `For ${plural(toNumber(form.span_length) ?? 1, spanUnit(form))}`
    case 'every_n_months': return `For ${plural(toNumber(form.every_months) ?? 1, 'month')}`
    default: return `In ${startLabel(form, fiscalStartMonth)}`
  }
}

function customPhrase(form) {
  const first = form.start_date ? formatDate(form.start_date) : NO_START
  const last = form.end_date ? formatDate(form.end_date) : '(no end date yet)'
  return `From ${first} to ${last}`
}

function isRecurring(form) {
  return form.recurring && form.period_type !== 'custom'
}

function periodPhrase(form, fiscalStartMonth) {
  if (form.period_type === 'custom') return customPhrase(form)
  return isRecurring(form) ? recurringPhrase(form) : oneTimePhrase(form, fiscalStartMonth)
}

function tailPhrase(form, fiscalStartMonth) {
  if (isRecurring(form)) {
    const end = form.end_date ? `until ${formatDate(form.end_date)}` : 'no end date'
    return `, starting ${startLabel(form, fiscalStartMonth)}, ${end}`
  }
  if (form.period_type === 'custom' || NAMED_PERIODS.has(form.period_type)) return ''
  return `, starting ${startLabel(form, fiscalStartMonth)}`
}

function whoPhrase(form, pilots) {
  if (form.all_pilots) return 'all active pilots'
  const names = form.pilot_ids.map(id => pilots.find(p => p.id === id)?.full_name).filter(Boolean)
  if (form.pilot_ids.length === 0) return 'no pilots yet'
  if (names.length === form.pilot_ids.length && names.length <= 3) return joinList(names, 'and')
  return plural(form.pilot_ids.length, 'selected pilot')
}

function durationText(minutes) {
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  const parts = []
  if (hours) parts.push(plural(hours, 'hour'))
  if (rest) parts.push(`${rest} min`)
  return parts.join(' ')
}

/** "1 hour 30 min", "3 flights", "15 min and 2 flights". */
export function targetText(minutes, flights) {
  const parts = []
  if (minutes) parts.push(durationText(minutes))
  if (flights) parts.push(plural(flights, 'flight'))
  return parts.length ? parts.join(' and ') : 'no target yet'
}

function aircraftPhrase(form) {
  switch (form.model_mode) {
    case 'combined': return `on ${joinList(form.models, 'or')}`
    case 'each': return `on each of: ${form.models.join(', ')}`
    case 'each_all_active': return 'on each active model'
    default: return 'on any aircraft'
  }
}

function timePhrase(form) {
  if (form.time_mode === 'night') return ' at night'
  if (form.time_mode !== 'clock') return ''
  return ` between ${clockText(form.window_start_time)} and ${clockText(form.window_end_time)}`
}

function purposePhrase(form) {
  return form.purposes.length ? ` (purpose: ${joinList(form.purposes, 'or')})` : ''
}

/** "any 90 days", "any month". */
function rollingWindowPhrase(form) {
  const length = toNumber(form.span_length) ?? 1
  return length === 1 ? `any ${spanUnit(form)}` : `any ${plural(length, spanUnit(form))}`
}

/** "All active pilots must have 1 hour on any aircraft in any 90 days, from Dec 1, 2026." */
function describeRolling(form, pilots) {
  const target = targetText(targetMinutesOf(form), toNumber(form.target_flights))
  const from = form.start_date ? formatDate(form.start_date) : NO_START
  return [
    capitalize(whoPhrase(form, pilots)), ' must have ', target, ' ', aircraftPhrase(form), timePhrase(form),
    purposePhrase(form), ' in ', rollingWindowPhrase(form), ', from ', from, '.',
  ].join('')
}

/**
 * The live summary of a requirement form, for example "Every quarter, all
 * active pilots must fly 15 min on each of: X10, X2E, starting Q4 2026, no end
 * date." A rolling window reads "All active pilots must have 1 hour on any
 * aircraft in any 90 days, from Dec 1, 2026." `pilots` names the selected pilots; `fiscalStartMonth` (1 to 12)
 * names fiscal periods.
 */
export function describeRequirement(form, { pilots = [], fiscalStartMonth = 10 } = {}) {
  if (form.period_type === 'rolling') return describeRolling(form, pilots)
  const target = targetText(targetMinutesOf(form), toNumber(form.target_flights))
  return [
    periodPhrase(form, fiscalStartMonth), ', ', whoPhrase(form, pilots), ' must fly ', target, ' ',
    aircraftPhrase(form), timePhrase(form), purposePhrase(form), tailPhrase(form, fiscalStartMonth), '.',
  ].join('')
}
