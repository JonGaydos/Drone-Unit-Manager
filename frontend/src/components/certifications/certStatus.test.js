import { describe, it, expect } from 'vitest'
import { addDays, todayLocal } from '@/lib/utils'
import { groupByUrgency } from './certStatus'

const CT = { id: 1, name: 'Part 107' }

// The group one complete certification lands in, expiring `days` from today.
function groupFor(days) {
  const rows = [{ pilot_id: 5, pilot_name: 'Ada Lovelace', certs: {
    1: { id: 100, status: 'complete', expiration_date: addDays(todayLocal(), days) },
  } }]
  const groups = groupByUrgency(rows, [CT], 'all', {})
  return Object.keys(groups).find(key => groups[key].length > 0)
}

describe('groupByUrgency boundaries', () => {
  it('puts a certification that expired yesterday in Expired', () => {
    expect(groupFor(-1)).toBe('expired')
  })

  it('puts a certification expiring today in the 30-day group', () => {
    expect(groupFor(0)).toBe('within30')
  })

  it('puts exactly 30 days in the 30-day group', () => {
    expect(groupFor(30)).toBe('within30')
  })

  it('puts 31 days in the 60-day group', () => {
    expect(groupFor(31)).toBe('within60')
  })

  it('puts exactly 60 days in the 60-day group', () => {
    expect(groupFor(60)).toBe('within60')
  })

  it('puts exactly 90 days in the 90-day group', () => {
    expect(groupFor(90)).toBe('within90')
  })

  it('puts 91 days in Current', () => {
    expect(groupFor(91)).toBe('current')
  })
})
