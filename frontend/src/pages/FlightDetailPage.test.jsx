import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderRoute } from '@/test/render'
import { setDisplayTimezone } from '@/lib/utils'
import FlightDetailPage from './FlightDetailPage'

// Mount endpoints (Promise.all in the load effect):
//   GET /flights/:id                          (primary; 500 -> "Flight not found")
//   GET /telemetry/flight/:id                 (.catch -> [])
//   GET /pilots /vehicles /flights/purposes/list
//   GET /batteries /sensors /attachments      (.catch -> [])
//   GET /photos?flight_id=:id                 (LinkedPhotos, .catch -> [])
const FLIGHT = {
  id: 1, external_id: 'abcdef123456', date: '2026-05-01', pilot_id: 5, pilot_name: 'Jane Doe',
  vehicle_id: 2, vehicle_name: 'Falcon', purpose: 'Patrol', duration_seconds: 600,
  takeoff_address: 'Main St', review_status: 'needs_review', has_telemetry: false,
}

function mockMount(overrides = {}) {
  const base = {
    flight: () => HttpResponse.json(FLIGHT),
    ...overrides,
  }
  server.use(
    http.get('/api/flights/:id', base.flight),
    http.get('/api/telemetry/flight/:id', () => HttpResponse.json([])),
    http.get('/api/pilots', () => HttpResponse.json([{ id: 5, full_name: 'Jane Doe', is_active: true }])),
    http.get('/api/vehicles', () => HttpResponse.json([{ id: 2, nickname: 'Falcon', model: 'Mavic 3' }])),
    http.get('/api/flights/purposes/list', () => HttpResponse.json([{ id: 1, name: 'Patrol' }])),
    http.get('/api/batteries', () => HttpResponse.json([])),
    http.get('/api/sensors', () => HttpResponse.json([])),
    http.get('/api/attachments', () => HttpResponse.json([])),
    http.get('/api/photos', () => HttpResponse.json([])),
  )
}

function render(role = 'admin') {
  return renderRoute(<FlightDetailPage />, { path: '/flights/:id', route: '/flights/1', role })
}

describe('FlightDetailPage', () => {
  beforeEach(() => setDisplayTimezone('America/Chicago'))
  afterEach(() => setDisplayTimezone(null))

  it('renders takeoff time in the configured zone and saves UTC', async () => {
    let patchBody = null
    mockMount({ flight: () => HttpResponse.json({ ...FLIGHT, takeoff_time: '2026-05-01T18:30:00Z' }) })
    server.use(http.patch('/api/flights/:id', async ({ request }) => {
      patchBody = await request.json()
      return HttpResponse.json({ ...FLIGHT, review_status: 'reviewed' })
    }))
    const { user } = render('admin')

    // 18:30 UTC on 2026-05-01 is 1:30 PM CDT.
    expect(await screen.findByText('1:30 PM')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Edit' }))
    await user.click(await screen.findByRole('button', { name: 'Save' }))
    // The edit form pre-filled 13:30 (zoned) and must post 18:30Z back.
    expect(patchBody.takeoff_time).toBe('2026-05-01T18:30:00Z')
  })

  it('renders without crashing', async () => {
    mockMount()
    render()
    expect(await screen.findByText('Flight on 2026-05-01')).toBeInTheDocument()
  })

  it('loads and renders the flight detail from a populated payload', async () => {
    mockMount()
    render()
    expect(await screen.findByText('Flight on 2026-05-01')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Jane Doe' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Falcon' })).toBeInTheDocument()
    expect(screen.getByText('No telemetry data available for this flight.')).toBeInTheDocument()
  })

  it('shows the no-telemetry empty state', async () => {
    mockMount()
    render()
    expect(await screen.findByText('No telemetry data available for this flight.')).toBeInTheDocument()
  })

  it('shows "Flight not found" when the primary endpoint 500s', async () => {
    mockMount({ flight: () => HttpResponse.json({ detail: 'boom' }, { status: 500 }) })
    render()
    expect(await screen.findByText('Flight not found')).toBeInTheDocument()
  })

  it('opens the edit form and PATCHes /flights/:id on save (admin)', async () => {
    let patchBody = null
    mockMount()
    server.use(http.patch('/api/flights/:id', async ({ request }) => {
      patchBody = await request.json()
      return HttpResponse.json({ ...FLIGHT, review_status: 'reviewed' })
    }))
    const { user } = render('admin')

    await screen.findByText('Flight on 2026-05-01')
    await user.click(screen.getByRole('button', { name: 'Edit' }))
    await user.click(await screen.findByRole('button', { name: 'Save' }))

    expect(patchBody).not.toBeNull()
    expect(patchBody.purpose).toBe('Patrol')
  })

  it('approves a needs_review flight via PATCH /flights/:id (admin)', async () => {
    let patchBody = null
    mockMount()
    server.use(http.patch('/api/flights/:id', async ({ request }) => {
      patchBody = await request.json()
      return HttpResponse.json({ ...FLIGHT, review_status: 'reviewed' })
    }))
    const { user } = render('admin')

    await screen.findByText('Flight on 2026-05-01')
    await user.click(screen.getByRole('button', { name: 'Approve Flight' }))

    expect(patchBody).toEqual({ review_status: 'reviewed', pilot_confirmed: true })
  })
  // Regression: view and edit used to be two different layouts, so pressing Edit
  // reshuffled every field. They now share one grid; the cells that have a
  // read-only counterpart must keep their order, and the value must become an
  // editable control in place.
  it('keeps the field order and container when switching into edit mode', async () => {
    mockMount()
    const { user } = render('admin')
    await screen.findByText('Flight on 2026-05-01')

    // Cell captions are <p> when read-only and <label> when they front a
    // control, so match on the shared caption class instead of the tag.
    const labelsIn = (root) => [...root.querySelectorAll(':scope > div > .text-xs')]
      .map(el => el.textContent.trim()).filter(t => t && t !== ' ')

    const gridSelector = '.grid.grid-cols-2'
    const viewLabels = labelsIn(document.querySelector(gridSelector))
    expect(viewLabels.slice(0, 4)).toEqual(['Pilot', 'Vehicle', 'Purpose', 'Duration'])

    await user.click(screen.getByRole('button', { name: 'Edit' }))

    const editGrid = document.querySelector(gridSelector)
    const editLabels = labelsIn(editGrid)
    // Duration gains its unit hint; every other shared cell keeps its label and
    // position, and the edit-only cells are appended rather than inserted.
    expect(editLabels.slice(0, 4)).toEqual(['Pilot', 'Vehicle', 'Purpose', 'Duration (seconds)'])
    expect(editLabels.indexOf('Takeoff Time')).toBe(viewLabels.indexOf('Takeoff Time'))
    expect(editLabels.indexOf('Max Speed')).toBe(viewLabels.indexOf('Max Speed'))
    // Status fills the trailing gap of the attachment row rather than claiming a
    // row of its own, so it lands after every shared cell but before Notes.
    expect(editLabels.indexOf('Status')).toBeGreaterThan(editLabels.indexOf('Attachment (RIGHT)'))
    expect(editLabels.indexOf('Status')).toBeLessThan(editLabels.indexOf('Notes'))
    expect(editLabels.at(-1)).toBe('Notes')

    // The Pilot cell now holds a control rather than static text.
    expect(screen.getByLabelText('Pilot').tagName).toBe('SELECT')
    // Telemetry-derived values stay read-only in both modes.
    expect(screen.queryByLabelText('Max Speed')).toBeNull()
  })

  // A flight can be dropped from the unit's numbers on its own, for a one-off
  // that is not the unit's activity: a vendor demo flown by one of our people.
  describe('unit totals', () => {
    it('says so on a flight that is not counted', async () => {
      mockMount({ flight: () => HttpResponse.json({ ...FLIGHT, counts_toward_totals: false }) })
      render('admin')

      await screen.findByText('Flight on 2026-05-01')
      expect(screen.getByText('Not counted')).toBeInTheDocument()
    })

    it('stays quiet on an ordinary flight', async () => {
      mockMount()
      render('admin')

      await screen.findByText('Flight on 2026-05-01')
      expect(screen.queryByText('Not counted')).toBeNull()
    })

    it('sends the flag when it is turned off while editing', async () => {
      let patchBody = null
      mockMount()
      server.use(http.patch('/api/flights/:id', async ({ request }) => {
        patchBody = await request.json()
        return HttpResponse.json(FLIGHT)
      }))
      const { user } = render('admin')

      await screen.findByText('Flight on 2026-05-01')
      await user.click(screen.getByRole('button', { name: 'Edit' }))
      await user.click(await screen.findByLabelText('Unit totals'))
      await user.click(screen.getByRole('button', { name: 'Save' }))

      expect(patchBody.counts_toward_totals).toBe(false)
    })
  })
})
