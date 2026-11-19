import { describe, it, expect } from 'vitest'
import { duplicateOf, formProblem, fromRequirement, fromTemplate, newForm, toBody, toDefinition, withModels } from './formState'

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

  it('names a duplicate "Copy of ..."', () => {
    expect(duplicateOf(REQ).name).toBe('Copy of Night currency')
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
})
