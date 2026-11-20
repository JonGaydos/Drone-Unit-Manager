import { describe, it, expect } from 'vitest'
import {
  duplicateOf, firstPeriodEnd, formProblem, fromRequirement, fromTemplate, newForm, startsInPast, toBody, toDefinition,
  withModels,
} from './formState'
import { todayLocal } from '@/lib/utils'

const REQ = {
  id: 4, name: 'Night currency', description: null, period_type: 'monthly_window', recurring: true,
  window_start_day: 19, window_end_day: 5, span_length: null, span_unit: null, every_months: null,
  target_minutes: 90, target_flights: null, model_mode: 'combined', models: ['X10'], time_mode: 'clock',
  window_start_time: '18:00:00', window_end_time: '02:00:00', purposes: ['Patrol'], pilot_ids: [3],
  reminder_days: 5, is_active: false, start_date: '2026-11-19', end_date: null,
}

describe('form state', () => {
  it('round-trips a requirement into the body the API takes', () => {
    expect(toBody(fromRequirement(REQ))).toEqual({
      name: 'Night currency', description: null, period_type: 'monthly_window', recurring: true,
      window_start_day: 19, window_end_day: 5, span_length: null, span_unit: null, every_months: null,
      target_minutes: 90, target_flights: null, model_mode: 'combined', models: ['X10'], time_mode: 'clock',
      window_start_time: '18:00', window_end_time: '02:00', purposes: ['Patrol'], reminder_days: 5,
      is_active: false, start_date: '2026-11-19', end_date: null, pilot_ids: [3],
    })
  })

  it('names a duplicate "Copy of ..." and starts it today', () => {
    const copy = duplicateOf({ ...REQ, start_date: '2026-01-01' })
    expect(copy.name).toBe('Copy of Night currency')
    expect(copy.start_date).toBe(todayLocal())
  })

  it('finds the end of the first period for each period type', () => {
    const form = (patch) => ({ ...newForm(), start_date: '2026-05-20', ...patch })
    expect(firstPeriodEnd(form({}), 10)).toBe('2026-05-31')
    expect(firstPeriodEnd(form({ period_type: 'calendar_quarter' }), 10)).toBe('2026-06-30')
    expect(firstPeriodEnd(form({ period_type: 'calendar_year' }), 10)).toBe('2026-12-31')
    expect(firstPeriodEnd(form({ period_type: 'fiscal_quarter' }), 10)).toBe('2026-06-30')
    expect(firstPeriodEnd(form({ period_type: 'fiscal_year' }), 10)).toBe('2026-09-30')
    expect(firstPeriodEnd(form({ period_type: 'fiscal_year' }), 4)).toBe('2027-03-31')
    expect(firstPeriodEnd(form({ period_type: 'every_n_months', every_months: '2' }), 10)).toBe('2026-07-19')
    expect(firstPeriodEnd(form({ period_type: 'span', span_length: '2', span_unit: 'weeks' }), 10)).toBe('2026-06-02')
    expect(firstPeriodEnd(form({ period_type: 'span', span_length: '1', span_unit: 'months' }), 10)).toBe('2026-06-19')
    expect(firstPeriodEnd(form({ period_type: 'monthly_window', window_start_day: '19', window_end_day: '5' }), 10))
      .toBe('2026-07-05')
    expect(firstPeriodEnd(form({ period_type: 'monthly_window', window_start_day: '21', window_end_day: '28' }), 10))
      .toBe('2026-05-28')
    expect(firstPeriodEnd(form({ period_type: 'custom', end_date: '2026-08-01' }), 10)).toBe('2026-08-01')
    expect(firstPeriodEnd(form({ start_date: '' }), 10)).toBeNull()
  })

  it('says a requirement starts in the past only when its first period has ended', () => {
    const form = { ...newForm(), start_date: '2026-10-15' }
    expect(startsInPast(form, 10, '2026-10-31')).toBe(false)
    expect(startsInPast(form, 10, '2026-11-01')).toBe(true)
    expect(startsInPast({ ...form, start_date: '' }, 10, '2026-11-01')).toBe(false)
  })

  it('fills from a template without dates or pilots', () => {
    const f = fromTemplate({ id: 1, name: 'T', settings: toDefinition(fromRequirement(REQ)) })
    expect(f.name).toBe('Night currency')
    expect(f.start_date).toBe('')
    expect(f.end_date).toBe('')
    expect(f.all_pilots).toBe(true)
    expect(f.pilot_ids).toEqual([])
  })

  it('keeps the model mode consistent with the number of models', () => {
    const base = newForm()
    expect(withModels(base, ['X10']).model_mode).toBe('combined')
    expect(withModels({ ...base, model_mode: 'each' }, ['X10', 'X2E']).model_mode).toBe('each')
    expect(withModels({ ...base, model_mode: 'each' }, ['X10']).model_mode).toBe('combined')
    expect(withModels({ ...base, model_mode: 'combined' }, []).model_mode).toBe('all')
  })

  it('sends no models for all aircraft or every active model', () => {
    expect(toDefinition({ ...newForm(), model_mode: 'each_all_active', models: ['X10', 'X2E'] }).models).toEqual([])
  })

  it('names the first problem before saving', () => {
    expect(formProblem({ ...newForm(), name: ' ' })).toBe('Enter a name')
    expect(formProblem({ ...newForm(), name: 'A' })).toBe('Set a target in hours and minutes, flights or both')
    expect(formProblem({ ...newForm(), name: 'A', target_flights: '1', all_pilots: false })).toBe('Select at least one pilot')
    expect(formProblem({ ...newForm(), name: 'A', target_flights: '1' })).toBeNull()
  })

  it('sends the end date only when the period uses it', () => {
    const recurring = { ...newForm(), name: 'A', target_flights: '1', start_date: '2026-11-01', end_date: '2027-01-31' }
    expect(toBody(recurring).end_date).toBe('2027-01-31')
    expect(toBody({ ...recurring, recurring: false }).end_date).toBeNull()
    expect(toBody({ ...recurring, recurring: false, period_type: 'custom' }).end_date).toBe('2027-01-31')
  })

  it('sends the span fields for a span period', () => {
    const body = toBody({ ...newForm(), period_type: 'span', span_length: '2', span_unit: 'months', every_months: '4', window_start_day: '3' })
    expect(body).toMatchObject({
      period_type: 'span', span_length: 2, span_unit: 'months', every_months: null, window_start_day: null, window_end_day: null,
    })
  })

  it('sends every_months for an every-N-months period', () => {
    const body = toBody({ ...newForm(), period_type: 'every_n_months', every_months: '3', span_length: '2', span_unit: 'weeks' })
    expect(body).toMatchObject({
      period_type: 'every_n_months', every_months: 3, span_length: null, span_unit: null, window_start_day: null, window_end_day: null,
    })
  })
})

