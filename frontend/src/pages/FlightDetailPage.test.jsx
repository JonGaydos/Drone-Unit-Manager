import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { fleetOptions, pilotOption, vehicleOption } from '@/test/options'
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
    http.get('/api/pilots/options', () => HttpResponse.json([pilotOption(5, 'Jane Doe')])),
    http.get('/api/fleet/options', () => HttpResponse.json(fleetOptions({ vehicles: [vehicleOption({ id: 2, nickname: 'Falcon', model: 'Mavic 3' })] }))),
    http.get('/api/flights/purposes/list', () => HttpResponse.json([{ id: 1, name: 'Patrol' }])),
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
    // The edit form pre-fills 13:30 (zoned); 14:00 there must post as 19:00Z.
    const takeoff = await screen.findByLabelText('Takeoff Time')
    expect(takeoff).toHaveValue('2026-05-01T13:30')
    fireEvent.change(takeoff, { target: { value: '2026-05-01T14:00' } })
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(patchBody.takeoff_time).toBe('2026-05-01T19:00:00Z'))
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
    await user.type(await screen.findByLabelText('Case #'), 'C-9')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(patchBody).toEqual({ case_number: 'C-9' }))
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
  it('shows and edits landing address, coordinates, distance and operating cost', async () => {
    let patchBody = null
    mockMount({ flight: () => HttpResponse.json({
      ...FLIGHT, landing_address: 'North Field', takeoff_lat: 44.5, takeoff_lon: -93.25,
      landing_lat: 44.6, landing_lon: -93.2, distance_m: 1200, operating_cost: 35.5,
    }) })
    server.use(http.patch('/api/flights/:id', async ({ request }) => {
      patchBody = await request.json()
      return HttpResponse.json(FLIGHT)
    }))
    const { user } = render('admin')
    expect(await screen.findByText('North Field')).toBeInTheDocument()
    expect(screen.getByText('44.5, -93.25')).toBeInTheDocument()
    expect(screen.getByText('44.6, -93.2')).toBeInTheDocument()
    expect(screen.getByText('1200 m')).toBeInTheDocument()
    expect(screen.getByText('$35.50')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Edit' }))
    await user.clear(screen.getByLabelText('Landing'))
    await user.type(screen.getByLabelText('Landing'), 'South Field')
    await user.clear(screen.getByLabelText('Takeoff Latitude'))
    await user.type(screen.getByLabelText('Takeoff Latitude'), '45')
    await user.clear(screen.getByLabelText('Landing Longitude'))
    await user.clear(screen.getByLabelText('Distance (m)'))
    await user.type(screen.getByLabelText('Distance (m)'), '1500')
    await user.clear(screen.getByLabelText('Operating Cost ($)'))
    await user.type(screen.getByLabelText('Operating Cost ($)'), '40')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(patchBody).toEqual({
      landing_address: 'South Field', takeoff_lat: 45, landing_lon: null, distance_m: 1500, operating_cost: 40,
    }))
  })

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

  it('at own edit, offers Edit on the own flight without Status, Unit totals or the pilot picker', async () => {
    mockMount()
    const { user } = renderRoute(<FlightDetailPage />, {
      path: '/flights/:id', route: '/flights/1', user: { id: 3, username: 'p', role: 'pilot', pilot_id: 5 },
    })
    await user.click(await screen.findByRole('button', { name: 'Edit' }))
    expect(screen.queryByLabelText('Status')).toBeNull()
    expect(screen.queryByLabelText(/Counts/)).toBeNull()
    expect(screen.queryByLabelText('Pilot')).toBeNull()
    expect(screen.getByLabelText('Vehicle')).toBeInTheDocument()
  })

  it("does not offer Edit on another pilot's flight at own", async () => {
    mockMount()
    renderRoute(<FlightDetailPage />, {
      path: '/flights/:id', route: '/flights/1', user: { id: 3, username: 'p', role: 'pilot', pilot_id: 99 },
    })
    await screen.findByText(/Flight on/)
    expect(screen.queryByRole('button', { name: 'Edit' })).toBeNull()
  })

  it('saving a reviewed flight unchanged sends nothing, with times that have seconds', async () => {
    let patched = false
    mockMount({
      flight: () => HttpResponse.json({ ...FLIGHT, review_status: 'reviewed', purpose: null, takeoff_time: '2026-05-01T18:30:42Z', landing_time: '2026-05-01T18:45:17Z' }),
    })
    server.use(http.patch('/api/flights/:id', () => { patched = true; return HttpResponse.json(FLIGHT) }))
    const { user } = renderRoute(<FlightDetailPage />, {
      path: '/flights/:id', route: '/flights/1', user: { id: 3, username: 'p', role: 'pilot', pilot_id: 5 },
    })
    await user.click(await screen.findByRole('button', { name: 'Edit' }))
    await user.click(await screen.findByRole('button', { name: 'Save' }))
    await screen.findByRole('button', { name: 'Edit' })
    expect(patched).toBe(false)
  })

  it('says a reviewed flight is back for review when an edit sends it there', async () => {
    const reviewed = { ...FLIGHT, review_status: 'reviewed' }
    mockMount({ flight: () => HttpResponse.json(reviewed) })
    server.use(http.patch('/api/flights/:id', () => HttpResponse.json({ ...reviewed, case_number: 'C-9', review_status: 'needs_review' })))
    const { user } = renderRoute(<FlightDetailPage />, {
      path: '/flights/:id', route: '/flights/1', user: { id: 3, username: 'p', role: 'pilot', pilot_id: 5 },
    })
    await user.click(await screen.findByRole('button', { name: 'Edit' }))
    await user.type(await screen.findByLabelText('Case #'), 'C-9')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText(/back for review.*does not count toward currency until reviewed/i)).toBeInTheDocument()
  })

  it.each(['/api/fleet/options', '/api/pilots/options', '/api/flights/purposes/list'])('stays rendered with the flight when %s 500s', async (path) => {
    mockMount()
    server.use(http.get(path, () => HttpResponse.json({ detail: 'boom' }, { status: 500 })))
    const { user } = render('admin')
    expect(await screen.findByText('Flight on 2026-05-01')).toBeInTheDocument()
    expect(screen.queryByText('Flight not found')).toBeNull()
    await user.click(screen.getByRole('button', { name: 'Edit' }))
    expect(await screen.findByLabelText('Case #')).toBeInTheDocument()
  })
})
