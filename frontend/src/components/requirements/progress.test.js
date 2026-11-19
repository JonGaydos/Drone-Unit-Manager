import { describe, it, expect } from 'vitest'
import { daysLeftText, durationText, excuseAction, excusalText, metCount, progressText } from './progress'

describe('durationText', () => {
  it('writes minutes as hours and minutes', () => {
    expect(durationText(12)).toBe('12m')
    expect(durationText(60)).toBe('1h')
    expect(durationText(85)).toBe('1h 25m')
    expect(durationText(0)).toBe('0m')
    expect(durationText(1200)).toBe('20h')
  })

  it('drops partial minutes so an unmet target never rounds up to it', () => {
    expect(durationText(59.9)).toBe('59m')
  })
})

describe('progressText', () => {
  it('writes a large target in hours on both sides of the fraction', () => {
    expect(progressText({ '*': { minutes: 430, flights: 9 } }, { '*': false }, { target_minutes: 1200 })).toBe('7h 10m/20h')
  })

  it('names each model with its minutes, and "done" once met', () => {
    const totals = { X10: { minutes: 12.8, flights: 2 }, X2E: { minutes: 20, flights: 1 } }
    expect(progressText(totals, { X10: false, X2E: true }, { target_minutes: 15 })).toBe('X10 12m/15m, X2E done')
  })

  it('leaves out the model name for all aircraft and combined models', () => {
    expect(progressText({ '*': { minutes: 30, flights: 1 } }, { '*': false }, { target_minutes: 60 })).toBe('30m/1h')
    expect(progressText({ '*': { minutes: 60, flights: 1 } }, { '*': true }, { target_minutes: 60 })).toBe('done')
  })

  it('counts flights against a flight target, and both when both are set', () => {
    const totals = { '*': { minutes: 5, flights: 1 } }
    expect(progressText(totals, {}, { target_flights: 3 })).toBe('1/3 flights')
    expect(progressText(totals, {}, { target_minutes: 15, target_flights: 1 })).toBe('5m/15m 1/1 flights')
  })

  it('shows the amounts without "done" when no met map is given, as for saved history', () => {
    expect(progressText({ X10: { minutes: 18, flights: 2 } }, null, { target_minutes: 15 })).toBe('X10 18m/15m')
  })

  it('gives the plain amounts when the target is not known', () => {
    expect(progressText({ '*': { minutes: 25.5, flights: 1 } }, null, {})).toBe('25m 1 flight')
  })

  it('says nothing was flown when there are no totals', () => {
    expect(progressText({}, {}, { target_minutes: 15 })).toBe('Nothing flown yet')
    expect(progressText(null, null, { target_minutes: 15 })).toBe('Nothing flown yet')
  })
})

describe('excusalText', () => {
  it('labels an automatic excusal apart from one a supervisor made', () => {
    expect(excusalText({ excused: true, excused_by_id: null, excused_reason: 'Added after the period started' }))
      .toBe('Excused automatically: Added after the period started')
    expect(excusalText({ excused: true, excused_by_id: 4, excused_reason: 'On leave' })).toBe('Excused: On leave')
  })

  it('reads as a plain excusal when the row does not say who excused it', () => {
    expect(excusalText({ excused: true, excused_reason: 'On leave' })).toBe('Excused: On leave')
    expect(excusalText({ excused: true, excused_by_id: 2, excused_reason: null })).toBe('Excused')
  })

  it('is empty for a row that is not excused', () => {
    expect(excusalText({ excused: false, excused_reason: null })).toBe('')
  })
})

describe('excuseAction', () => {
  it('offers un-excuse on an excused row, excuse on one not met, and nothing on a met row', () => {
    expect(excuseAction({ excused: true, status: 'excused' })).toBe('unexcuse')
    expect(excuseAction({ excused: true, status: 'met' })).toBe('unexcuse')
    expect(excuseAction({ excused: false, status: 'missed' })).toBe('excuse')
    expect(excuseAction({ excused: false, status: 'on_track' })).toBe('excuse')
    expect(excuseAction({ excused: false, status: 'met' })).toBeNull()
  })
})

describe('daysLeftText and metCount', () => {
  it('words the days left in a period', () => {
    expect(daysLeftText(12)).toBe('12 days left')
    expect(daysLeftText(1)).toBe('Last day')
    expect(daysLeftText(0)).toBe('Ended')
  })

  it('counts the pilots who met the target', () => {
    expect(metCount([{ status: 'met' }, { status: 'on_track' }, { status: 'met' }])).toBe(2)
  })
})
