/**
 * The requirement builder's form state and its conversion to and from the API.
 *
 * Inputs hold strings, so the form keeps numbers as text and splits the
 * minutes target into hours and minutes. `all_pilots` stands for an empty
 * `pilot_ids` (all active pilots) so a "Selected pilots" choice with nobody
 * ticked yet is not mistaken for it.
 */
import { addDays, addMonths, todayLocal } from '@/lib/utils'

// The period fields each period type uses; the others are sent as null.
const PERIOD_FIELDS = {
  monthly_window: ['window_start_day', 'window_end_day'],
  span: ['span_length', 'span_unit'],
  rolling: ['span_length', 'span_unit'],
  every_n_months: ['every_months'],
}
const ALL_PERIOD_FIELDS = ['window_start_day', 'window_end_day', 'span_length', 'span_unit', 'every_months']
// Period types that never repeat as separate periods: a custom range runs once, a rolling window is continuous.
const NOT_RECURRING = new Set(['custom', 'rolling'])
// Modes whose model list is stored; "all" and "each_all_active" store none.
const LISTED_MODES = new Set(['combined', 'each'])

/** A blank form for a new requirement, starting today. */
export function newForm() {
  return {
    name: '', description: '', period_type: 'calendar_month', recurring: true,
    window_start_day: '', window_end_day: '', span_length: '', span_unit: 'weeks', every_months: '',
    target_hours: '', target_mins: '', target_flights: '',
    model_mode: 'all', models: [], time_mode: 'any', window_start_time: '', window_end_time: '',
    purposes: [], all_pilots: true, pilot_ids: [], reminder_days: '7', is_active: true,
    start_date: todayLocal(), end_date: '',
  }
}

function toNumber(value) {
  const n = Number.parseInt(value, 10)
  return Number.isNaN(n) ? null : n
}

function text(value) {
  return value === null || value === undefined ? '' : String(value)
}

/** The minutes target the hours and minutes fields add up to, or null. */
export function targetMinutesOf(form) {
  const total = (toNumber(form.target_hours) ?? 0) * 60 + (toNumber(form.target_mins) ?? 0)
  return total > 0 ? total : null
}

/** Set the model list and keep the mode valid for its length. */
export function withModels(form, models) {
  let mode = form.model_mode
  if (models.length === 0) mode = 'all'
  else if (models.length === 1 || mode === 'all') mode = 'combined'
  return { ...form, models, model_mode: mode }
}

function periodFields(form) {
  const used = PERIOD_FIELDS[form.period_type] || []
  return Object.fromEntries(ALL_PERIOD_FIELDS.map(name => {
    if (!used.includes(name)) return [name, null]
    return [name, name === 'span_unit' ? form.span_unit : toNumber(form[name])]
  }))
}

function timeFields(form) {
  const clock = form.time_mode === 'clock'
  return {
    time_mode: form.time_mode,
    window_start_time: clock ? form.window_start_time || null : null,
    window_end_time: clock ? form.window_end_time || null : null,
  }
}

/** Every setting except the dates and pilots: what a template holds. */
export function toDefinition(form) {
  return {
    name: form.name.trim(),
    description: form.description.trim() || null,
    period_type: form.period_type,
    recurring: NOT_RECURRING.has(form.period_type) ? false : form.recurring,
    ...periodFields(form),
    target_minutes: targetMinutesOf(form),
    target_flights: toNumber(form.target_flights) || null,
    model_mode: form.model_mode,
    models: LISTED_MODES.has(form.model_mode) ? form.models : [],
    ...timeFields(form),
    purposes: form.purposes,
    reminder_days: toNumber(form.reminder_days) ?? 7,
    is_active: form.is_active,
  }
}

function usesEndDate(form) {
  if (form.period_type === 'rolling') return false
  return form.period_type === 'custom' || form.recurring
}

/** The body for POST /api/requirements or PATCH /api/requirements/{id}. */
export function toBody(form) {
  return {
    ...toDefinition(form),
    start_date: form.start_date,
    // The end date field shows only for a custom or recurring period; a one-time
    // or rolling period sends none, so a date set before switching is not kept.
    end_date: usesEndDate(form) ? form.end_date || null : null,
    pilot_ids: form.all_pilots ? [] : form.pilot_ids,
  }
}

function fromDefinition(def) {
  const minutes = def.target_minutes || 0
  return {
    name: def.name, description: text(def.description), period_type: def.period_type,
    recurring: def.recurring,
    window_start_day: text(def.window_start_day), window_end_day: text(def.window_end_day),
    span_length: text(def.span_length), span_unit: def.span_unit || 'weeks', every_months: text(def.every_months),
    target_hours: minutes >= 60 ? String(Math.floor(minutes / 60)) : '',
    target_mins: minutes % 60 ? String(minutes % 60) : '',
    target_flights: text(def.target_flights),
    model_mode: def.model_mode, models: [...def.models], time_mode: def.time_mode,
    window_start_time: text(def.window_start_time).slice(0, 5), window_end_time: text(def.window_end_time).slice(0, 5),
    purposes: [...def.purposes], reminder_days: text(def.reminder_days), is_active: def.is_active,
  }
}

/** A saved requirement as form state, for editing. */
export function fromRequirement(req) {
  return {
    ...newForm(),
    ...fromDefinition(req),
    all_pilots: req.pilot_ids.length === 0,
    pilot_ids: [...req.pilot_ids],
    start_date: req.start_date,
    end_date: text(req.end_date),
  }
}

/** A new requirement filled from another, named "Copy of ...", starting today. */
export function duplicateOf(req) {
  return { ...fromRequirement(req), name: `Copy of ${req.name}`, start_date: todayLocal() }
}

/** A new requirement filled from a template: no dates, all active pilots. */
export function fromTemplate(template) {
  return { ...newForm(), ...fromDefinition(template.settings), start_date: '', end_date: '' }
}

/** The first thing to fix before saving, or null. The API checks the rest. */
export function formProblem(form) {
  if (!form.name.trim()) return 'Enter a name'
  if (!form.start_date) return 'Choose a start date'
  if (form.period_type === 'custom' && !form.end_date) return 'Choose an end date for a custom range'
  if (form.period_type === 'rolling' && !toNumber(form.span_length)) return 'Set the window length'
  if (!targetMinutesOf(form) && !toNumber(form.target_flights)) return 'Set a target in hours and minutes, flights or both'
  if (!form.all_pilots && form.pilot_ids.length === 0) return 'Select at least one pilot'
  return null
}

// The end of the first period, by period type, as the backend lays periods out
// (requirement_periods.py). Dates are 'YYYY-MM-DD' strings.

function ymd(year, month, day) {
  return `${String(year).padStart(4, '0')}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
}

function parts(date) {
  return date.split('-').map(Number)
}

function mod(n, m) {
  return ((n % m) + m) % m
}

/** The day `day` of the month `index` months after year 0, clamped to the month's length. */
function clampedDay(index, day) {
  const year = Math.floor(index / 12)
  const month = mod(index, 12) + 1
  const lastDay = new Date(Date.UTC(year, month, 0)).getUTCDate()
  return ymd(year, month, Math.min(day, lastDay))
}

function monthsEnd(anchor, months) {
  return addDays(addMonths(anchor, months), -1)
}

const CALENDAR_LENGTH = { calendar_month: 1, calendar_quarter: 3, calendar_year: 12, fiscal_quarter: 3, fiscal_year: 12 }

function calendarEnd(form, fiscalStartMonth) {
  const [year, month] = parts(form.start_date)
  const length = CALENDAR_LENGTH[form.period_type]
  let firstMonth = 1
  if (form.period_type.startsWith('fiscal')) {
    firstMonth = mod(month - mod(mod(month - fiscalStartMonth, 12), length) - 1, 12) + 1
  } else if (length < 12) {
    firstMonth = month - mod(month - 1, length)
  }
  const anchorYear = firstMonth > month ? year - 1 : year
  return monthsEnd(ymd(anchorYear, firstMonth, 1), length)
}

function spanEnd(form) {
  const length = toNumber(form.span_length) || 1
  if (form.span_unit === 'months') return monthsEnd(form.start_date, length)
  return addDays(form.start_date, length * (form.span_unit === 'weeks' ? 7 : 1) - 1)
}

function windowEnd(form) {
  const startDay = toNumber(form.window_start_day) || 1
  const endDay = toNumber(form.window_end_day) || startDay
  const [year, month] = parts(form.start_date)
  let index = year * 12 + month - 1
  if (clampedDay(index, startDay) < form.start_date) index += 1
  if (endDay >= startDay) return clampedDay(index, endDay)
  const last = clampedDay(index + 1, endDay)
  const nextStart = clampedDay(index + 1, startDay)
  return last < nextStart ? last : addDays(nextStart, -1)
}

const FIRST_END = {
  ...Object.fromEntries(Object.keys(CALENDAR_LENGTH).map(type => [type, calendarEnd])),
  every_n_months: form => monthsEnd(form.start_date, toNumber(form.every_months) || 1),
  span: spanEnd,
  monthly_window: windowEnd,
  custom: form => form.end_date || form.start_date,
}

/** The last day of the form's first period, or null without a start date. */
export function firstPeriodEnd(form, fiscalStartMonth) {
  if (!form.start_date) return null
  return FIRST_END[form.period_type]?.(form, fiscalStartMonth) ?? null
}

/** Whether the form's first period ended before `today`: saving counts, flags and emails those periods. */
export function startsInPast(form, fiscalStartMonth, today = todayLocal()) {
  const end = firstPeriodEnd(form, fiscalStartMonth)
  return end !== null && end < today
}
