/**
 * The requirement builder's form state and its conversion to and from the API.
 *
 * Inputs hold strings, so the form keeps numbers as text and splits the
 * minutes target into hours and minutes. `all_pilots` stands for an empty
 * `pilot_ids` (all active pilots) so a "Selected pilots" choice with nobody
 * ticked yet is not mistaken for it.
 */
import { todayLocal } from '@/lib/utils'

// The period fields each period type uses; the others are sent as null.
const PERIOD_FIELDS = {
  monthly_window: ['window_start_day', 'window_end_day'],
  span: ['span_length', 'span_unit'],
  every_n_months: ['every_months'],
}
const ALL_PERIOD_FIELDS = ['window_start_day', 'window_end_day', 'span_length', 'span_unit', 'every_months']
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
    recurring: form.period_type === 'custom' ? false : form.recurring,
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
  return form.period_type === 'custom' || form.recurring
}

/** The body for POST /api/requirements or PATCH /api/requirements/{id}. */
export function toBody(form) {
  return {
    ...toDefinition(form),
    start_date: form.start_date,
    // The end date field shows only for a custom or recurring period; a one-time
    // period sends none, so a date set before switching to One time is not kept.
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

/** A new requirement filled from another, named "Copy of ...". */
export function duplicateOf(req) {
  return { ...fromRequirement(req), name: `Copy of ${req.name}` }
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
  if (!targetMinutesOf(form) && !toNumber(form.target_flights)) return 'Set a target in hours and minutes, flights or both'
  if (!form.all_pilots && form.pilot_ids.length === 0) return 'Select at least one pilot'
  return null
}
