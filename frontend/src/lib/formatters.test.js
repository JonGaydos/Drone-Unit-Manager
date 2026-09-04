import { describe, it, expect } from 'vitest'
import {
  sortByName,
  sortPilots,
  sortVehicles,
  sortByField,
  sortPilotsActiveFirst,
  vehicleDisplayName,
  equipmentDisplayName,
  formatStatusText,
} from '@/lib/formatters'

describe('sortByName', () => {
  it('sorts by full_name by default without mutating input', () => {
    const input = [{ full_name: 'Charlie' }, { full_name: 'Alice' }, { full_name: 'Bob' }]
    const result = sortByName(input)
    expect(result.map(x => x.full_name)).toEqual(['Alice', 'Bob', 'Charlie'])
    expect(input.map(x => x.full_name)).toEqual(['Charlie', 'Alice', 'Bob'])
  })

  it('sorts by a custom key', () => {
    const result = sortByName([{ name: 'Zed' }, { name: 'Ann' }], 'name')
    expect(result.map(x => x.name)).toEqual(['Ann', 'Zed'])
  })

  it('treats missing name as empty string', () => {
    const result = sortByName([{ full_name: 'Bob' }, {}])
    expect(result.map(x => x.full_name || '')).toEqual(['', 'Bob'])
  })
})

describe('sortPilots', () => {
  it('sorts pilots by full_name', () => {
    const result = sortPilots([{ full_name: 'Bravo' }, { full_name: 'Alpha' }])
    expect(result.map(x => x.full_name)).toEqual(['Alpha', 'Bravo'])
  })
})

describe('sortVehicles', () => {
  it('sorts by "manufacturer model" string', () => {
    const result = sortVehicles([
      { manufacturer: 'DJI', model: 'Mavic' },
      { manufacturer: 'Autel', model: 'Evo' },
    ])
    expect(result.map(v => v.manufacturer)).toEqual(['Autel', 'DJI'])
  })
})

describe('sortByField', () => {
  it('sorts by the name field by default', () => {
    const result = sortByField([{ name: 'Beta' }, { name: 'Alpha' }])
    expect(result.map(x => x.name)).toEqual(['Alpha', 'Beta'])
  })

  it('sorts by a custom field', () => {
    const result = sortByField([{ label: 'Z' }, { label: 'A' }], 'label')
    expect(result.map(x => x.label)).toEqual(['A', 'Z'])
  })
})

describe('sortPilotsActiveFirst', () => {
  it('puts active pilots before inactive ones', () => {
    const result = sortPilotsActiveFirst([
      { status: 'inactive', first_name: 'Alice' },
      { status: 'active', first_name: 'Bob' },
    ])
    expect(result.map(p => p.first_name)).toEqual(['Bob', 'Alice'])
  })

  it('sorts by first_name within the same status', () => {
    const result = sortPilotsActiveFirst([
      { status: 'active', first_name: 'Charlie' },
      { status: 'active', first_name: 'Alice' },
    ])
    expect(result.map(p => p.first_name)).toEqual(['Alice', 'Charlie'])
  })

  it('orders active group before inactive group with internal sort', () => {
    const result = sortPilotsActiveFirst([
      { status: 'inactive', first_name: 'Zed' },
      { status: 'active', first_name: 'Bob' },
      { status: 'inactive', first_name: 'Ann' },
      { status: 'active', first_name: 'Amy' },
    ])
    expect(result.map(p => p.first_name)).toEqual(['Amy', 'Bob', 'Ann', 'Zed'])
  })
})

describe('vehicleDisplayName', () => {
  it('prefers nickname', () => {
    expect(vehicleDisplayName({ nickname: 'Falcon', manufacturer: 'DJI', model: 'Mavic' })).toBe('Falcon')
  })

  it('falls back to manufacturer + model', () => {
    expect(vehicleDisplayName({ manufacturer: 'DJI', model: 'Mavic' })).toBe('DJI Mavic')
  })

  it('falls back to serial number when no nickname or make/model', () => {
    expect(vehicleDisplayName({ serial_number: 'SN-1' })).toBe('SN-1')
  })

  it('returns "Unknown" when no fields present', () => {
    expect(vehicleDisplayName({})).toBe('Unknown')
  })
})

describe('equipmentDisplayName', () => {
  it('prefers nickname', () => {
    expect(equipmentDisplayName({ nickname: 'Cam1', serial_number: 'SN-9' })).toBe('Cam1')
  })

  it('falls back to serial number before make/model', () => {
    expect(equipmentDisplayName({ serial_number: 'SN-9', manufacturer: 'DJI', model: 'X' })).toBe('SN-9')
  })

  it('falls back to manufacturer + model', () => {
    expect(equipmentDisplayName({ manufacturer: 'DJI', model: 'X' })).toBe('DJI X')
  })

  it('returns "Unknown" when no fields present', () => {
    expect(equipmentDisplayName({})).toBe('Unknown')
  })
})

describe('formatStatusText', () => {
  it('converts snake_case to Title Case', () => {
    expect(formatStatusText('in_progress')).toBe('In Progress')
  })

  it('title-cases a single word', () => {
    expect(formatStatusText('active')).toBe('Active')
  })

  it('does NOT split kebab-case (only underscores are replaced)', () => {
    // The code only replaces underscores, so the hyphen is preserved.
    // \b\w title-cases the first letter after the hyphen boundary too.
    expect(formatStatusText('needs-review')).toBe('Needs-Review')
  })

  it('returns empty string for falsy input', () => {
    expect(formatStatusText('')).toBe('')
    expect(formatStatusText(null)).toBe('')
    expect(formatStatusText(undefined)).toBe('')
  })
})
