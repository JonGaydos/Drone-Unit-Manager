import { describe, it, expect } from 'vitest'
import { describeRequirement, startLabel, targetText } from './RequirementSummary'
import { newForm } from './formState'

const OPTIONS = { pilots: [], fiscalStartMonth: 10 }

function form(overrides) {
  return { ...newForm(), start_date: '', ...overrides }
}

describe('describeRequirement', () => {
  it('describes a recurring quarter on each of several models', () => {
    const text = describeRequirement(form({
      name: 'Quarterly models', period_type: 'calendar_quarter', recurring: true, target_mins: '15',
      model_mode: 'each', models: ['X10', 'X2E', 'LEMUR 2'], start_date: '2026-10-01',
    }), OPTIONS)
    expect(text).toBe('Every quarter, all active pilots must fly 15 min on each of: X10, X2E, LEMUR 2, starting Q4 2026, no end date.')
  })

  it('describes a monthly window with a clock window', () => {
    const text = describeRequirement(form({
      name: 'Overnight', period_type: 'monthly_window', recurring: true, window_start_day: '19',
      window_end_day: '5', target_hours: '1', time_mode: 'clock', window_start_time: '00:00',
      window_end_time: '06:00', start_date: '2026-11-19',
    }), OPTIONS)
    expect(text).toBe('Every month from the 19th to the 5th of the following month, all active pilots must fly 1 hour on any aircraft between 12:00 AM and 6:00 AM, starting Nov 19, 2026, no end date.')
  })

  it('describes a one-time calendar month without a start tail', () => {
    const text = describeRequirement(form({ period_type: 'calendar_month', recurring: false, target_hours: '1', start_date: '2026-10-15' }), OPTIONS)
    expect(text).toBe('In October 2026, all active pilots must fly 1 hour on any aircraft.')
  })

  it('names selected pilots, combined models, night, purposes, flights and an end date', () => {
    const text = describeRequirement(form({
      period_type: 'span', recurring: true, span_length: '2', span_unit: 'weeks', target_hours: '1',
      target_mins: '30', target_flights: '3', model_mode: 'combined', models: ['X10', 'X2E'], time_mode: 'night',
      purposes: ['Patrol', 'Training'], all_pilots: false, pilot_ids: [1, 2], start_date: '2026-11-02', end_date: '2027-03-01',
    }), { pilots: [{ id: 1, full_name: 'Pat Pilot' }, { id: 2, full_name: 'Sam Flyer' }], fiscalStartMonth: 10 })
    expect(text).toBe('Every 2 weeks, Pat Pilot and Sam Flyer must fly 1 hour 30 min and 3 flights on X10 or X2E at night (purpose: Patrol or Training), starting Nov 2, 2026, until Mar 1, 2027.')
  })

  it('describes a custom range by its dates and every active model', () => {
    const text = describeRequirement(form({
      period_type: 'custom', target_flights: '1', model_mode: 'each_all_active', start_date: '2026-12-01', end_date: '2026-12-31',
    }), OPTIONS)
    expect(text).toBe('From Dec 1, 2026 to Dec 31, 2026, all active pilots must fly 1 flight on each active model.')
  })
})

describe('describeRequirement for a rolling window', () => {
  it('describes a rolling window from its start date', () => {
    const text = describeRequirement(form({
      period_type: 'rolling', recurring: false, span_length: '90', span_unit: 'days', target_hours: '1', start_date: '2026-12-01',
    }), OPTIONS)
    expect(text).toBe('All active pilots must have 1 hour on any aircraft in any 90 days, from Dec 1, 2026.')
  })

  it('names selected pilots, night, purposes and a single unit', () => {
    const text = describeRequirement(form({
      period_type: 'rolling', span_length: '1', span_unit: 'months', target_flights: '3', time_mode: 'night',
      purposes: ['Patrol'], all_pilots: false, pilot_ids: [1], start_date: '',
    }), { pilots: [{ id: 1, full_name: 'Pat Pilot' }], fiscalStartMonth: 10 })
    expect(text).toBe('Pat Pilot must have 3 flights on any aircraft at night (purpose: Patrol) in any month, from (no start date yet).')
  })
})

describe('startLabel', () => {
  it('labels fiscal periods by the fiscal year they end in', () => {
    expect(startLabel({ period_type: 'fiscal_quarter', start_date: '2026-11-19' }, 10)).toBe('Q1 FY2027')
    expect(startLabel({ period_type: 'fiscal_year', start_date: '2026-09-30' }, 10)).toBe('FY2026')
    expect(startLabel({ period_type: 'fiscal_quarter', start_date: '2026-05-01' }, 1)).toBe('Q2 FY2026')
    expect(startLabel({ period_type: 'calendar_year', start_date: '2026-05-01' }, 10)).toBe('2026')
  })
})

describe('targetText', () => {
  it('reads minutes and flights', () => {
    expect(targetText(120, null)).toBe('2 hours')
    expect(targetText(null, 1)).toBe('1 flight')
    expect(targetText(null, null)).toBe('no target yet')
  })
})
