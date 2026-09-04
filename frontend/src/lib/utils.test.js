import { describe, it, expect, afterEach } from 'vitest'
import {
  cn,
  formatDuration,
  formatHours,
  metersToFeet,
  mpsToMph,
  formatDate,
  daysUntil,
  formatDateTime,
  normalizeDateValue,
  setDisplayTimezone,
  getDisplayTimezone,
  formatTime,
  utcIsoToZonedInput,
  zonedInputToUtcIso,
  TIMEZONES,
} from '@/lib/utils'

describe('cn', () => {
  it('merges multiple class strings', () => {
    expect(cn('px-2', 'py-1')).toBe('px-2 py-1')
  })

  it('resolves conflicting tailwind classes to the last one', () => {
    expect(cn('px-2', 'px-4')).toBe('px-4')
  })

  it('applies conditional classes from objects', () => {
    expect(cn('base', { active: true, hidden: false })).toBe('base active')
  })
})

describe('formatDuration', () => {
  it('formats hours and minutes when over an hour', () => {
    expect(formatDuration(2 * 3600 + 15 * 60)).toBe('2h 15m')
  })

  it('formats minutes and seconds when under an hour', () => {
    expect(formatDuration(5 * 60 + 30)).toBe('5m 30s')
  })

  it('returns em-dash for zero', () => {
    expect(formatDuration(0)).toBe('—')
  })

  it('returns em-dash for null/undefined', () => {
    expect(formatDuration(null)).toBe('—')
    expect(formatDuration(undefined)).toBe('—')
  })
})

describe('formatHours', () => {
  it('converts seconds to one-decimal hours', () => {
    expect(formatHours(9000)).toBe('2.5')
  })

  it('returns "0.0" for zero/falsy', () => {
    expect(formatHours(0)).toBe('0.0')
    expect(formatHours(null)).toBe('0.0')
    expect(formatHours(undefined)).toBe('0.0')
  })
})

describe('metersToFeet', () => {
  it('converts 1 meter to 3 feet (rounded)', () => {
    expect(metersToFeet(1)).toBe(3)
  })

  it('converts 100 meters rounded to nearest integer', () => {
    expect(metersToFeet(100)).toBe(328)
  })

  it('returns 0 for zero meters', () => {
    expect(metersToFeet(0)).toBe(0)
  })

  it('returns null for null/undefined', () => {
    expect(metersToFeet(null)).toBeNull()
    expect(metersToFeet(undefined)).toBeNull()
  })
})

describe('mpsToMph', () => {
  it('converts 10 m/s to mph rounded to one decimal', () => {
    expect(mpsToMph(10)).toBe(22.4)
  })

  it('returns 0 for zero', () => {
    expect(mpsToMph(0)).toBe(0)
  })

  it('returns null for null/undefined', () => {
    expect(mpsToMph(null)).toBeNull()
    expect(mpsToMph(undefined)).toBeNull()
  })
})

describe('formatDate', () => {
  it('formats a date-only ISO string without timezone shift', () => {
    expect(formatDate('2026-03-26')).toBe('Mar 26, 2026')
  })

  it('formats a full datetime ISO string', () => {
    expect(formatDate('2026-03-26T15:45:00')).toBe('Mar 26, 2026')
  })

  it('returns em-dash for null/empty', () => {
    expect(formatDate(null)).toBe('—')
    expect(formatDate('')).toBe('—')
    expect(formatDate(undefined)).toBe('—')
  })

  it('returns em-dash for an invalid date string', () => {
    expect(formatDate('not-a-date')).toBe('—')
  })
})

describe('daysUntil', () => {
  function isoOffsetFromToday(days) {
    const d = new Date()
    d.setHours(0, 0, 0, 0)
    d.setDate(d.getDate() + days)
    const yr = d.getFullYear()
    const mo = String(d.getMonth() + 1).padStart(2, '0')
    const day = String(d.getDate()).padStart(2, '0')
    return `${yr}-${mo}-${day}`
  }

  it('returns 0 for today', () => {
    expect(daysUntil(isoOffsetFromToday(0))).toBe(0)
  })

  it('returns positive for a future date', () => {
    expect(daysUntil(isoOffsetFromToday(5))).toBe(5)
  })

  it('returns negative for a past date', () => {
    expect(daysUntil(isoOffsetFromToday(-3))).toBe(-3)
  })

  it('returns null for null/empty', () => {
    expect(daysUntil(null)).toBeNull()
    expect(daysUntil('')).toBeNull()
  })

  it('returns null for an invalid date string', () => {
    expect(daysUntil('not-a-date')).toBeNull()
  })
})

describe('formatDateTime', () => {
  it('formats a datetime ISO string with date and time', () => {
    expect(formatDateTime('2026-03-26T15:45:00')).toBe('Mar 26, 2026, 3:45 PM')
  })

  it('returns em-dash for null/empty', () => {
    expect(formatDateTime(null)).toBe('—')
    expect(formatDateTime('')).toBe('—')
  })

  it('returns em-dash for an invalid date string', () => {
    expect(formatDateTime('not-a-date')).toBe('—')
  })
})

describe('normalizeDateValue', () => {
  it('fixes 00xx years below 50 to 20xx', () => {
    expect(normalizeDateValue('0026-12-12')).toBe('2026-12-12')
  })

  it('fixes 00xx years 50 and above to 19xx', () => {
    expect(normalizeDateValue('0099-01-01')).toBe('1999-01-01')
  })

  it('leaves a normal four-digit year unchanged', () => {
    expect(normalizeDateValue('2026-12-12')).toBe('2026-12-12')
  })

  it('returns falsy input unchanged', () => {
    expect(normalizeDateValue('')).toBe('')
    expect(normalizeDateValue(null)).toBeNull()
    expect(normalizeDateValue(undefined)).toBeUndefined()
  })
})

describe('timezone-aware formatting (America/Chicago)', () => {
  afterEach(() => setDisplayTimezone(null))

  it('formatDateTime converts a UTC Z instant to the configured zone', () => {
    setDisplayTimezone('America/Chicago')
    // 16:26 UTC on 2026-06-24 is 11:26 CDT (UTC-5).
    expect(formatDateTime('2026-06-24T16:26:00Z')).toBe('Jun 24, 2026, 11:26 AM')
  })

  it('formatTime converts a UTC Z instant to the configured zone', () => {
    setDisplayTimezone('America/Chicago')
    expect(formatTime('2026-06-24T16:26:00Z')).toBe('11:26 AM')
    expect(formatTime(null)).toBe('—')
  })

  it('utcIsoToZonedInput yields a datetime-local wall value in the zone', () => {
    expect(utcIsoToZonedInput('2026-06-24T16:26:00Z', 'America/Chicago')).toBe('2026-06-24T11:26')
  })

  it('zonedInputToUtcIso round-trips a zoned wall value back to UTC Z', () => {
    expect(zonedInputToUtcIso('2026-06-24T11:26', 'America/Chicago')).toBe('2026-06-24T16:26:00Z')
  })

  it('exposes America/Chicago in the TIMEZONES list', () => {
    expect(TIMEZONES).toContain('America/Chicago')
  })
})

describe('invalid configured timezone falls back to browser-local', () => {
  afterEach(() => setDisplayTimezone(null))

  it('formatDateTime does not throw and returns a non-empty string', () => {
    setDisplayTimezone('Not/AZone')
    expect(() => formatDateTime('2026-06-24T16:26:00Z')).not.toThrow()
    expect(formatDateTime('2026-06-24T16:26:00Z')).not.toBe('')
  })

  it('formatTime does not throw and returns a non-empty string', () => {
    setDisplayTimezone('Not/AZone')
    expect(() => formatTime('2026-06-24T16:26:00Z')).not.toThrow()
    expect(formatTime('2026-06-24T16:26:00Z')).not.toBe('')
  })

  it('utcIsoToZonedInput does not throw and returns a wall value', () => {
    setDisplayTimezone('Not/AZone')
    expect(() => utcIsoToZonedInput('2026-06-24T16:26:00Z')).not.toThrow()
    expect(utcIsoToZonedInput('2026-06-24T16:26:00Z')).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/)
  })

  it('zonedInputToUtcIso does not throw and returns a valid UTC Z instant', () => {
    setDisplayTimezone('Not/AZone')
    expect(() => zonedInputToUtcIso('2026-06-24T11:26')).not.toThrow()
    expect(zonedInputToUtcIso('2026-06-24T11:26')).toMatch(/Z$/)
  })
})
