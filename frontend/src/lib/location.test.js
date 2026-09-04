import { describe, it, expect } from 'vitest'
import { resolveOrgLocation, DEFAULT_ORG_LOCATION } from '@/lib/location'

describe('DEFAULT_ORG_LOCATION', () => {
  it('is the White House center', () => {
    expect(DEFAULT_ORG_LOCATION).toEqual({
      lat: 38.8977,
      lon: -77.0365,
      name: 'White House, Washington D.C.',
    })
  })
})

describe('resolveOrgLocation', () => {
  it('returns provided coords and name when all settings present', () => {
    const settings = [
      { key: 'org_default_lat', value: '40.5' },
      { key: 'org_default_lon', value: '-74.2' },
      { key: 'org_location_name', value: 'HQ' },
    ]
    expect(resolveOrgLocation(settings)).toEqual({ lat: 40.5, lon: -74.2, name: 'HQ' })
  })

  it('derives a name from coords when name is absent', () => {
    const settings = [
      { key: 'org_default_lat', value: '40.5' },
      { key: 'org_default_lon', value: '-74.2' },
    ]
    expect(resolveOrgLocation(settings)).toEqual({ lat: 40.5, lon: -74.2, name: '40.5, -74.2' })
  })

  it('falls back to default when settings is undefined', () => {
    expect(resolveOrgLocation(undefined)).toEqual(DEFAULT_ORG_LOCATION)
  })

  it('falls back to default when settings is empty', () => {
    expect(resolveOrgLocation([])).toEqual(DEFAULT_ORG_LOCATION)
  })

  it('falls back to default when only latitude is present', () => {
    const settings = [{ key: 'org_default_lat', value: '40.5' }]
    expect(resolveOrgLocation(settings)).toEqual(DEFAULT_ORG_LOCATION)
  })

  it('falls back to default when coords are unparseable', () => {
    const settings = [
      { key: 'org_default_lat', value: 'abc' },
      { key: 'org_default_lon', value: 'xyz' },
    ]
    expect(resolveOrgLocation(settings)).toEqual(DEFAULT_ORG_LOCATION)
  })

  it('returns a fresh copy of the default (not the shared reference)', () => {
    expect(resolveOrgLocation([])).not.toBe(DEFAULT_ORG_LOCATION)
  })
})
