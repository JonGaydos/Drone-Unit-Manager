import { describe, it, expect } from 'vitest'
import { groupByFeature, setCell, cellState, diffChanges } from './permissionGrid'

const def = (key, feature, action, kind, requires = null, viewer_locked = false) => (
  { key, feature, action, kind, defaults: {}, viewer_locked, requires }
)
const REGISTRY = [
  def('fleet.view', 'Fleet equipment', 'View', 'bool'),
  def('fleet.manage', 'Fleet equipment', 'Manage', 'bool', 'fleet.view', true),
  def('checkouts.use', 'Equipment checkouts', 'Check out', 'bool', 'fleet.view', true),
  def('flights.view', 'Flights', 'View', 'bool'),
  def('flights.edit', 'Flights', 'Edit', 'level', 'flights.view', true),
]
const valuesFor = (over = {}) => ({
  admin: { 'fleet.view': 'yes', 'fleet.manage': 'yes', 'checkouts.use': 'yes', 'flights.view': 'yes', 'flights.edit': 'all' },
  supervisor: { 'fleet.view': 'yes', 'fleet.manage': 'yes', 'checkouts.use': 'yes', 'flights.view': 'yes', 'flights.edit': 'all' },
  pilot: { 'fleet.view': 'yes', 'fleet.manage': 'yes', 'checkouts.use': 'yes', 'flights.view': 'yes', 'flights.edit': 'own', ...over },
  viewer: { 'fleet.view': 'yes', 'fleet.manage': 'no', 'checkouts.use': 'no', 'flights.view': 'yes', 'flights.edit': 'none' },
})

describe('groupByFeature', () => {
  it('keeps registry order and groups rows by feature', () => {
    const groups = groupByFeature(REGISTRY)
    expect(groups.map(g => g.feature)).toEqual(['Fleet equipment', 'Equipment checkouts', 'Flights'])
    expect(groups[0].rows.map(r => r.key)).toEqual(['fleet.view', 'fleet.manage'])
  })
})

describe('setCell', () => {
  it('sets the value without touching the original', () => {
    const base = valuesFor()
    const next = setCell(base, REGISTRY, 'pilot', 'flights.edit', 'all')
    expect(next.pilot['flights.edit']).toBe('all')
    expect(base.pilot['flights.edit']).toBe('own')
  })

  it('turning a view off lowers every key that requires it, across features', () => {
    const next = setCell(valuesFor(), REGISTRY, 'pilot', 'fleet.view', 'no')
    expect(next.pilot['fleet.manage']).toBe('no')
    expect(next.pilot['checkouts.use']).toBe('no')
    expect(next.pilot['flights.edit']).toBe('own')
  })

  it('turning a view back on does not restore dependents', () => {
    const off = setCell(valuesFor(), REGISTRY, 'pilot', 'fleet.view', 'no')
    const on = setCell(off, REGISTRY, 'pilot', 'fleet.view', 'yes')
    expect(on.pilot['fleet.manage']).toBe('no')
  })

  it('lowers a level dependent to none', () => {
    const next = setCell(valuesFor(), REGISTRY, 'pilot', 'flights.view', 'no')
    expect(next.pilot['flights.edit']).toBe('none')
  })
})

describe('cellState', () => {
  it('locks the admin column', () => {
    const state = cellState(REGISTRY[0], 'admin', valuesFor(), REGISTRY)
    expect(state.disabled).toBe(true)
    expect(state.reason).toMatch(/always on/i)
  })

  it('locks viewer cells that the backend locks', () => {
    const state = cellState(REGISTRY[1], 'viewer', valuesFor(), REGISTRY)
    expect(state).toMatchObject({ disabled: true, reason: 'Viewers are read only' })
  })

  it('leaves unlocked viewer view cells editable', () => {
    expect(cellState(REGISTRY[0], 'viewer', valuesFor(), REGISTRY).disabled).toBe(false)
  })

  it('disables a dependent while its view is off, naming the view', () => {
    const off = setCell(valuesFor(), REGISTRY, 'pilot', 'fleet.view', 'no')
    const state = cellState(REGISTRY[2], 'pilot', off, REGISTRY)
    expect(state).toMatchObject({ disabled: true, reason: 'Needs Fleet equipment view on' })
    expect(cellState(REGISTRY[2], 'pilot', valuesFor(), REGISTRY).disabled).toBe(false)
  })
})

describe('diffChanges', () => {
  it('is empty without edits', () => {
    expect(diffChanges(valuesFor(), valuesFor(), REGISTRY)).toEqual([])
  })

  it('lists only changed cells', () => {
    const draft = setCell(valuesFor(), REGISTRY, 'pilot', 'flights.edit', 'all')
    expect(diffChanges(valuesFor(), draft, REGISTRY)).toEqual([
      { role: 'pilot', key: 'flights.edit', value: 'all' },
    ])
  })

  it('never sends admin or locked viewer cells', () => {
    const draft = valuesFor()
    draft.admin['flights.edit'] = 'none'
    draft.viewer['flights.edit'] = 'all'
    expect(diffChanges(valuesFor(), draft, REGISTRY)).toEqual([])
  })
})
