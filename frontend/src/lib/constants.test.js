import { describe, it, expect } from 'vitest'
import {
  STATUS_COLORS,
  CERT_STATUS_COLORS,
  OUTCOME_COLORS,
  MISSION_STATUS_COLORS,
  FREQUENCY_COLORS,
  EQUIPMENT_STATUSES,
  statusOptions,
} from '@/lib/constants'

function isNonEmptyStringMap(obj) {
  expect(typeof obj).toBe('object')
  expect(obj).not.toBeNull()
  const keys = Object.keys(obj)
  expect(keys.length).toBeGreaterThan(0)
  for (const k of keys) expect(typeof obj[k]).toBe('string')
}

describe('color constant maps', () => {
  it('STATUS_COLORS is a non-empty string map with expected keys and a default', () => {
    isNonEmptyStringMap(STATUS_COLORS)
    expect(STATUS_COLORS).toHaveProperty('active')
    expect(STATUS_COLORS).toHaveProperty('inactive')
    expect(STATUS_COLORS).toHaveProperty('_default')
  })

  it('CERT_STATUS_COLORS is a non-empty string map with expected keys', () => {
    isNonEmptyStringMap(CERT_STATUS_COLORS)
    expect(CERT_STATUS_COLORS).toHaveProperty('active')
    expect(CERT_STATUS_COLORS).toHaveProperty('expired')
  })

  it('OUTCOME_COLORS is a non-empty string map with expected keys', () => {
    isNonEmptyStringMap(OUTCOME_COLORS)
    expect(OUTCOME_COLORS).toHaveProperty('completed')
    expect(OUTCOME_COLORS).toHaveProperty('failed')
  })

  it('MISSION_STATUS_COLORS is a non-empty string map with expected keys', () => {
    isNonEmptyStringMap(MISSION_STATUS_COLORS)
    expect(MISSION_STATUS_COLORS).toHaveProperty('planned')
    expect(MISSION_STATUS_COLORS).toHaveProperty('cancelled')
  })

  it('FREQUENCY_COLORS is a non-empty string map with expected keys', () => {
    isNonEmptyStringMap(FREQUENCY_COLORS)
    expect(FREQUENCY_COLORS).toHaveProperty('monthly')
    expect(FREQUENCY_COLORS).toHaveProperty('yearly')
  })

})

describe('EQUIPMENT_STATUSES', () => {
  // Mirrors EQUIPMENT_STATUSES in backend/app/services/equipment_lifecycle.py.
  const values = (type) => EQUIPMENT_STATUSES[type].map(o => o.value)
  it('gives each fleet type the statuses the API accepts', () => {
    expect(values('vehicle')).toEqual(['active', 'maintenance', 'retired', 'damaged'])
    expect(values('battery')).toEqual(['active', 'charging', 'maintenance', 'retired', 'damaged'])
    expect(values('dock')).toEqual(['active', 'online', 'offline', 'maintenance', 'retired', 'damaged'])
    for (const type of ['controller', 'sensor', 'attachment', 'other']) {
      expect(values(type)).toEqual(['active', 'maintenance', 'retired', 'damaged'])
    }
  })

  it('keeps a stored status outside the list selectable', () => {
    expect(statusOptions('vehicle', 'inactive').map(o => o.value)).toEqual(['inactive', 'active', 'maintenance', 'retired', 'damaged'])
    expect(statusOptions('vehicle', 'active')).toEqual(EQUIPMENT_STATUSES.vehicle)
  })
})
