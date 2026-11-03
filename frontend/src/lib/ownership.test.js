import { describe, it, expect } from 'vitest'
import { ownsDocument, ownsFlight, ownsLog, ownsPilot, ownsRecord } from './ownership'

const me = { id: 3, pilot_id: 7 }
const noPilot = { id: 3, pilot_id: null }

describe('ownsFlight', () => {
  it('covers the linked pilot and flights the user logged', () => {
    expect(ownsFlight(me, { pilot_id: 7, created_by_id: null })).toBe(true)
    expect(ownsFlight(me, { pilot_id: 8, created_by_id: 3 })).toBe(true)
    expect(ownsFlight(me, { pilot_id: 8, created_by_id: 4 })).toBe(false)
  })

  it('a login with no linked pilot owns only what it logged', () => {
    expect(ownsFlight(noPilot, { pilot_id: null, created_by_id: null })).toBe(false)
    expect(ownsFlight(noPilot, { pilot_id: null, created_by_id: 3 })).toBe(true)
  })
})

describe('ownsLog', () => {
  it('covers the creator and a roster match', () => {
    expect(ownsLog(me, { created_by_id: 3, pilots: [] })).toBe(true)
    expect(ownsLog(me, { created_by_id: null, pilots: [{ pilot_id: 7 }] })).toBe(true)
    expect(ownsLog(me, { created_by_id: null, pilots: [{ pilot_id: 8 }] })).toBe(false)
    expect(ownsLog(noPilot, { created_by_id: null, pilots: [{ pilot_id: null }] })).toBe(false)
  })
})

describe('ownsRecord', () => {
  it('compares the owner field with the user id, and no owner is nobody', () => {
    expect(ownsRecord(me, 3)).toBe(true)
    expect(ownsRecord(me, 4)).toBe(false)
    expect(ownsRecord(me, null)).toBe(false)
    expect(ownsRecord(null, null)).toBe(false)
  })
})

describe('ownsPilot', () => {
  it('matches only the linked pilot', () => {
    expect(ownsPilot(me, 7)).toBe(true)
    expect(ownsPilot(me, 8)).toBe(false)
    expect(ownsPilot(noPilot, null)).toBe(false)
  })
})

describe('ownsDocument', () => {
  it('covers the uploader and the own pilot record', () => {
    expect(ownsDocument(me, { uploaded_by_id: 3 })).toBe(true)
    expect(ownsDocument(me, { uploaded_by_id: 4, pilot_id: 7 })).toBe(true)
    expect(ownsDocument(me, { uploaded_by_id: 4, pilot_id: 8 })).toBe(false)
    expect(ownsDocument(me, { uploaded_by_id: null, pilot_id: null })).toBe(false)
  })

  it('treats a certification document as possibly own when the user has a linked pilot', () => {
    expect(ownsDocument(me, { uploaded_by_id: 4, certification_id: 2 })).toBe(true)
    expect(ownsDocument(noPilot, { uploaded_by_id: 4, certification_id: 2 })).toBe(false)
  })
})
