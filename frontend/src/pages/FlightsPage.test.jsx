import { describe, it, expect } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { withPermissions } from '@/test/permissions'
import { fleetOptions, pilotOption, vehicleOption } from '@/test/options'
import { renderWithProviders } from '@/test/render'
import { zonedInputToUtcIso } from '@/lib/utils'
import FlightsPage from './FlightsPage'

// Mount endpoints (Promise.all in load()):
//   GET /flights?...                          -> { flights, total, total_pages }
//   GET /pilots /vehicles
//   GET /flights/purposes/list
//   GET /flights/count?review_status=needs_review -> { count }
//   GET /batteries /sensors /attachments      (each .catch(() => []))
// Bulk endpoints (supervisor-only UI):
//   POST /flights/bulk-update { flight_ids, ...patch }
//   POST /flights/bulk-delete { flight_ids }
const FLIGHTS = [
  { id: 1, external_id: 'abcdef1234', date: '2026-05-01', pilot_id: 5, pilot_name: 'Jane Doe', vehicle_id: 2, vehicle_name: 'Falcon', purpose: 'Patrol', duration_seconds: 600, takeoff_address: 'Main St', review_status: 'needs_review' },
  { id: 2, external_id: 'beef567890', date: '2026-05-02', pilot_id: 6, pilot_name: 'Bob Roy', vehicle_id: 3, vehicle_name: 'Hawk', purpose: 'Search', duration_seconds: 900, takeoff_address: 'Oak Ave', review_status: 'reviewed' },
]
const PILOTS = [pilotOption(5, 'Jane Doe'), pilotOption(6, 'Bob Roy')]
const VEHICLES = [vehicleOption({ id: 2, nickname: 'Falcon', model: 'Mavic 3' }), vehicleOption({ id: 3, nickname: 'Hawk', model: 'X10' })]
const PURPOSES = [{ id: 1, name: 'Patrol' }, { id: 2, name: 'Search' }]

function mockMount(overrides = {}) {
  const base = {
    flights: () => HttpResponse.json({ flights: FLIGHTS, total: FLIGHTS.length, total_pages: 1 }),
    pilots: () => HttpResponse.json(PILOTS),
    purposes: () => HttpResponse.json(PURPOSES),
    count: () => HttpResponse.json({ count: 1 }),
    ...overrides,
  }
  server.use(
    http.get('/api/flights', base.flights),
    http.get('/api/pilots/options', base.pilots),
    http.get('/api/fleet/options', () => HttpResponse.json(fleetOptions({ vehicles: VEHICLES }))),
    http.get('/api/flights/purposes/list', base.purposes),
    http.get('/api/flights/count', base.count),
  )
}

// Mount as a supervisor and tick every row, which is where every bulk action
// starts. Returns the userEvent instance for the rest of the interaction.
async function selectEveryRow() {
  const { user } = renderWithProviders(<FlightsPage />, { role: 'supervisor' })
  await user.click(await screen.findByLabelText('Select all flights on this page'))
  await screen.findByText(/\d+ selected/)
  return user
}

// The search box's debounce runs once after mount and sets page 1; let it pass
// before paging, so a test sees only the page changes it makes.
const settleSearchDebounce = () => new Promise(resolve => setTimeout(resolve, 350))

// Records the bulk-update POST body, or leaves it null if nothing was sent.
function captureBulkUpdate() {
  const sent = { body: null }
  server.use(http.post('/api/flights/bulk-update', async ({ request }) => {
    sent.body = await request.json()
    return HttpResponse.json({ updated: sent.body.flight_ids.length })
  }))
  return sent
}

describe('FlightsPage', () => {
  it('renders without crashing', async () => {
    mockMount()
    renderWithProviders(<FlightsPage />, { role: 'admin' })
    expect(await screen.findByRole('link', { name: 'Jane Doe' })).toBeInTheDocument()
  })

  it('loads and renders flight rows from a populated payload', async () => {
    mockMount()
    renderWithProviders(<FlightsPage />, { role: 'admin' })

    expect(await screen.findByRole('link', { name: 'Jane Doe' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Bob Roy' })).toBeInTheDocument()
    // Takeoff addresses render only in their rows (not in any dropdown).
    expect(screen.getByText('Main St')).toBeInTheDocument()
    expect(screen.getByText('Oak Ave')).toBeInTheDocument()
  })

  it('shows the empty state when there are no flights', async () => {
    mockMount({ flights: () => HttpResponse.json({ flights: [], total: 0, total_pages: 1 }) })
    renderWithProviders(<FlightsPage />, { role: 'admin' })
    expect(await screen.findByText('No flights found')).toBeInTheDocument()
  })

  it('shows the error banner when the primary endpoint 500s', async () => {
    mockMount({ flights: () => HttpResponse.json({ detail: 'flights boom' }, { status: 500 }) })
    renderWithProviders(<FlightsPage />, { role: 'admin' })
    expect(await screen.findByText('flights boom')).toBeInTheDocument()
  })

  it('searches on the server so every flight is covered, not just this page', async () => {
    let lastUrl = null
    mockMount({
      flights: ({ request }) => {
        lastUrl = new URL(request.url)
        const q = (lastUrl.searchParams.get('search') || '').toLowerCase()
        const rows = FLIGHTS.filter(f => f.pilot_name.toLowerCase().includes(q))
        return HttpResponse.json({ flights: rows, total: rows.length, total_pages: 1 })
      },
    })
    const { user } = renderWithProviders(<FlightsPage />, { role: 'admin' })

    await screen.findByRole('link', { name: 'Jane Doe' })
    await user.type(screen.getByPlaceholderText('Search flights...'), 'Bob')

    await waitFor(() => expect(screen.queryByRole('link', { name: 'Jane Doe' })).toBeNull())
    expect(screen.getByRole('link', { name: 'Bob Roy' })).toBeInTheDocument()
    expect(lastUrl.searchParams.get('search')).toBe('Bob')
    expect(lastUrl.searchParams.get('page')).toBe('1')
  })

  it('sorts on the server when a column header is clicked', async () => {
    let lastUrl = null
    mockMount({
      flights: ({ request }) => {
        lastUrl = new URL(request.url)
        return HttpResponse.json({ flights: FLIGHTS, total: FLIGHTS.length, total_pages: 1 })
      },
    })
    const { user } = renderWithProviders(<FlightsPage />, { role: 'admin' })
    await screen.findByRole('link', { name: 'Jane Doe' })

    await user.click(screen.getByText('Duration'))

    await waitFor(() => expect(lastUrl.searchParams.get('sort')).toBe('duration_seconds'))
    expect(lastUrl.searchParams.get('order')).toBe('asc')
  })

  it('fires the filtered request with the right query when the status filter changes', async () => {
    // Use a pilot so per-row status badges render as plain text, leaving the
    // status-filter "Reviewed" toggle as the only button with that name.
    server.use(http.get('/api/auth/me', () => HttpResponse.json(withPermissions({ id: 7, username: 'pilot', role: 'pilot' }))))
    let lastFlightsUrl = null
    mockMount({
      flights: ({ request }) => {
        lastFlightsUrl = new URL(request.url)
        return HttpResponse.json({ flights: FLIGHTS, total: FLIGHTS.length, total_pages: 1 })
      },
    })
    const { user } = renderWithProviders(<FlightsPage />, { role: 'pilot' })

    await screen.findByRole('link', { name: 'Jane Doe' })
    await user.click(screen.getByRole('button', { name: 'Reviewed' }))

    await screen.findByRole('link', { name: 'Jane Doe' })
    expect(lastFlightsUrl.searchParams.get('review_status')).toBe('reviewed')
  })

  it.each([
    ['Pilot', 'pilot-1', 'pilot_id', '6'],
    ['Vehicle', 'vehicle-1', 'vehicle_id', '3'],
    ['Purpose', 'purpose-1', 'purpose', 'Search'],
  ])('goes back to page 1 when the %s filter changes', async (_label, id, param, value) => {
    let lastUrl = null
    mockMount({
      flights: ({ request }) => {
        lastUrl = new URL(request.url)
        return HttpResponse.json({ flights: FLIGHTS, total: 500, total_pages: 5 })
      },
    })
    const { user, container } = renderWithProviders(<FlightsPage />, { role: 'admin' })
    await screen.findByRole('link', { name: 'Jane Doe' })
    await settleSearchDebounce()
    await user.click(screen.getByRole('button', { name: 'Next' }))
    await waitFor(() => expect(lastUrl.searchParams.get('page')).toBe('2'))

    await user.selectOptions(container.querySelector(`#${id}`), value)

    // The request that carries the new filter asks for page 1.
    await waitFor(() => expect(lastUrl.searchParams.get(param)).toBe(value))
    expect(lastUrl.searchParams.get('page')).toBe('1')
    expect(screen.getByText('Page 1 of 5')).toBeInTheDocument()
  })

  it('goes back to page 1 when a date filter changes', async () => {
    let lastUrl = null
    mockMount({
      flights: ({ request }) => {
        lastUrl = new URL(request.url)
        return HttpResponse.json({ flights: FLIGHTS, total: 500, total_pages: 5 })
      },
    })
    const { user } = renderWithProviders(<FlightsPage />, { role: 'admin' })
    await screen.findByRole('link', { name: 'Jane Doe' })
    await settleSearchDebounce()
    await user.click(screen.getByRole('button', { name: 'Next' }))
    await waitFor(() => expect(lastUrl.searchParams.get('page')).toBe('2'))

    await user.type(screen.getByLabelText('Date From'), '2026-05-01')

    await waitFor(() => expect(lastUrl.searchParams.get('date_from')).toBe('2026-05-01'))
    expect(lastUrl.searchParams.get('page')).toBe('1')
  })

  it('Add Flight sends times, notes, addresses, coordinates, distance and cost', async () => {
    let body = null
    mockMount()
    server.use(http.post('/api/flights', async ({ request }) => { body = await request.json(); return HttpResponse.json({ id: 9 }) }))
    const { user } = renderWithProviders(<FlightsPage />, { role: 'admin' })
    await screen.findByRole('link', { name: 'Jane Doe' })
    await user.click(screen.getByRole('button', { name: /Add Flight/ }))
    const form = (await screen.findAllByRole('button', { name: 'Add Flight' })).at(-1).closest('form')
    const f = (label) => within(form).getByLabelText(label)
    await user.type(f('Takeoff Time'), '2026-05-01T10:00')
    await user.type(f('Landing Time'), '2026-05-01T10:30')
    await user.type(f('Landing Address'), 'North Field')
    await user.type(f('Takeoff Latitude'), '44.5')
    await user.type(f('Takeoff Longitude'), '-93.25')
    await user.type(f('Landing Latitude'), '44.6')
    await user.type(f('Landing Longitude'), '-93.2')
    await user.type(f('Distance (m)'), '1200')
    await user.type(f('Operating Cost ($)'), '35.5')
    await user.type(f('Notes'), 'Hand entry')
    await user.click(within(form).getByRole('button', { name: 'Add Flight' }))

    await waitFor(() => expect(body).not.toBeNull())
    expect(body).toEqual({
      takeoff_time: zonedInputToUtcIso('2026-05-01T10:00'),
      landing_time: zonedInputToUtcIso('2026-05-01T10:30'),
      landing_address: 'North Field',
      takeoff_lat: 44.5, takeoff_lon: -93.25, landing_lat: 44.6, landing_lon: -93.2,
      distance_m: 1200, operating_cost: 35.5, notes: 'Hand entry',
    })
  })

  it('hides bulk-selection checkboxes from a pilot but shows them to a supervisor', async () => {
    server.use(http.get('/api/auth/me', () => HttpResponse.json(withPermissions({ id: 7, username: 'pilot', role: 'pilot' }))))
    mockMount()
    const { unmount } = renderWithProviders(<FlightsPage />, { role: 'pilot' })
    expect(await screen.findByRole('link', { name: 'Jane Doe' })).toBeInTheDocument()
    expect(screen.queryByLabelText('Select all flights on this page')).toBeNull()
    unmount()

    server.use(http.get('/api/auth/me', () => HttpResponse.json(withPermissions({ id: 8, username: 'sup', role: 'supervisor' }))))
    mockMount()
    renderWithProviders(<FlightsPage />, { role: 'supervisor' })
    expect(await screen.findByRole('link', { name: 'Jane Doe' })).toBeInTheDocument()
    expect(screen.getByLabelText('Select all flights on this page')).toBeInTheDocument()
  })

  it('hides the row delete control from a default pilot', async () => {
    mockMount()
    server.use(http.delete('/api/flights/:id', () => HttpResponse.json({ ok: true })))
    renderWithProviders(<FlightsPage />, { user: { id: 7, username: 'pilot', role: 'pilot', pilot_id: 5 } })
    await screen.findByRole('link', { name: 'Jane Doe' })
    expect(screen.queryByRole('button', { name: /^Delete flight/ })).toBeNull()
  })

  it('shows the row delete control at own on the own flight only, and deletes it', async () => {
    let deleted = null
    mockMount()
    server.use(http.delete('/api/flights/:id', ({ params }) => {
      deleted = params.id
      return HttpResponse.json({ ok: true })
    }))
    const { user } = renderWithProviders(<FlightsPage />, {
      user: { id: 7, username: 'pilot', role: 'pilot', pilot_id: 5 },
      permissions: { 'flights.delete': 'own' },
    })
    await screen.findByRole('link', { name: 'Jane Doe' })
    const control = screen.getAllByRole('button', { name: /^Delete flight/ })
    expect(control).toHaveLength(1)
    await user.click(control[0])
    await user.click(await screen.findByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(deleted).toBe('1'))
  })

  it('shows the edit control at own on the own flight only', async () => {
    mockMount()
    renderWithProviders(<FlightsPage />, { user: { id: 7, username: 'pilot', role: 'pilot', pilot_id: 5 } })
    await screen.findByRole('link', { name: 'Jane Doe' })
    expect(screen.getAllByRole('button', { name: 'Edit' })).toHaveLength(1)
  })

  it('at own edit, a pilot cannot reassign the flight in the edit row', async () => {
    mockMount()
    const { user } = renderWithProviders(<FlightsPage />, { user: { id: 7, username: 'pilot', role: 'pilot', pilot_id: 5 } })
    await screen.findByRole('link', { name: 'Jane Doe' })
    await user.click(screen.getByRole('button', { name: 'Edit' }))
    expect(screen.queryByLabelText('Pilot for this flight')).toBeNull()
    expect(within(screen.getByTitle('Save').closest('tr')).getByText('Jane Doe')).toBeInTheDocument()
  })

  it("fills the flight form's pilot picker from the options endpoint with pilots.view off", async () => {
    mockMount()
    server.use(http.get('/api/pilots', () => HttpResponse.json({ detail: 'no' }, { status: 403 })))
    const { user } = renderWithProviders(<FlightsPage />, {
      role: 'pilot',
      permissions: { 'pilots.view': 'no' },
    })
    await screen.findByRole('link', { name: 'Jane Doe' })
    await user.click(screen.getByRole('button', { name: /Add Flight/ }))
    const form = (await screen.findAllByRole('button', { name: 'Add Flight' })).at(-1).closest('form')
    expect(within(form).getByLabelText('Pilot')).toContainElement(within(form).getByRole('option', { name: 'Bob Roy' }))
  })

  it('bulk-delete (supervisor): selecting rows POSTs /flights/bulk-delete with the selected ids', async () => {
    let bulkBody = null
    mockMount()
    server.use(http.post('/api/flights/bulk-delete', async ({ request }) => {
      bulkBody = await request.json()
      return HttpResponse.json({ deleted: bulkBody.flight_ids.length })
    }))
    const { user } = renderWithProviders(<FlightsPage />, { role: 'supervisor' })

    await screen.findByRole('link', { name: 'Jane Doe' })
    // Select only flight #1 (external_id abcdef1234).
    await user.click(screen.getByLabelText('Select flight abcdef1234'))
    expect(await screen.findByText('1 selected')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Delete' }))  // toolbar button opens confirm
    // The confirm dialog adds a second "Delete" button; the dialog's is the last.
    await screen.findByText(/Permanently delete 1 selected flight/)
    const deletes = screen.getAllByRole('button', { name: 'Delete' })
    await user.click(deletes[deletes.length - 1])

    await screen.findByRole('link', { name: 'Jane Doe' })  // reloaded
    expect(bulkBody).toEqual({ flight_ids: [1] })
  })

  it('bulk-update (supervisor): "Mark reviewed" POSTs /flights/bulk-update with the selected ids', async () => {
    mockMount()
    const sent = captureBulkUpdate()
    const user = await selectEveryRow()

    await user.click(screen.getByRole('button', { name: 'Mark reviewed' }))
    // Every bulk edit is confirmed first.
    await screen.findByText(/Set the review status to "reviewed" on 2 selected/)
    await user.click(screen.getByRole('button', { name: 'Mark Reviewed' }))

    await screen.findByRole('link', { name: 'Jane Doe' })  // reloaded
    expect(sent.body.flight_ids.sort()).toEqual([1, 2])
    expect(sent.body.review_status).toBe('reviewed')
    expect(sent.body.pilot_confirmed).toBe(true)
  })

  // A bulk edit overwrites one field on every selected row in a single click.
  // On 2026-09-03 that silently replaced the purpose on 97 flights. The
  // confirmation has to name what is about to be replaced, not just the count.
  it('bulk purpose: the confirmation names what is being overwritten and how many rows change', async () => {
    mockMount()
    const sent = captureBulkUpdate()
    const user = await selectEveryRow()

    await user.selectOptions(screen.getByLabelText('Set purpose for selected flights'), 'Search')

    // Flight 2 is already "Search", so only one row actually changes.
    await screen.findByText(/Set the purpose to "Search" on 2 selected flight\(s\)\. 1 will change, replacing: Patrol \(1\)\./)
    expect(sent.body).toBeNull()
  })

  it('bulk purpose: nothing is sent when the confirmation is cancelled', async () => {
    mockMount()
    const sent = captureBulkUpdate()
    const user = await selectEveryRow()
    await user.selectOptions(screen.getByLabelText('Set purpose for selected flights'), 'Search')
    await screen.findByText(/Set the purpose to "Search"/)

    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(sent.body).toBeNull()
    expect(screen.queryByText(/Set the purpose to/)).toBeNull()
  })

  it('bulk purpose: confirming POSTs the selected ids and the new purpose', async () => {
    mockMount()
    const sent = captureBulkUpdate()
    const user = await selectEveryRow()
    await user.selectOptions(screen.getByLabelText('Set purpose for selected flights'), 'Search')
    await screen.findByText(/Set the purpose to "Search"/)

    await user.click(screen.getByRole('button', { name: 'Set Purpose' }))

    await screen.findByRole('link', { name: 'Jane Doe' })  // reloaded
    expect(sent.body.flight_ids.sort()).toEqual([1, 2])
    expect(sent.body.purpose).toBe('Search')
  })

  it('bulk pilot: the confirmation names the pilot and the ones being replaced', async () => {
    mockMount()
    const user = await selectEveryRow()

    await user.selectOptions(screen.getByLabelText('Reassign pilot for selected flights'), '5')

    // Flight 1 is already Jane Doe's, so only Bob Roy's row changes.
    expect(await screen.findByText(/Set the pilot to "Jane Doe" on 2 selected flight\(s\)\. 1 will change, replacing: Bob Roy \(1\)\./)).toBeInTheDocument()
  })

  it('says nothing will change when every selected row already holds the value', async () => {
    mockMount({ flights: () => HttpResponse.json({
      flights: FLIGHTS.map(f => ({ ...f, purpose: 'Search' })), total: 2, total_pages: 1 }) })
    const user = await selectEveryRow()

    await user.selectOptions(screen.getByLabelText('Set purpose for selected flights'), 'Search')

    expect(await screen.findByText(/All 2 selected flight\(s\) already have the purpose "Search"\. Nothing will change\./)).toBeInTheDocument()
  })

  it('caps the list of values being replaced', async () => {
    const many = Array.from({ length: 10 }, (_, i) => ({
      ...FLIGHTS[0], id: 10 + i, external_id: `id${i}`, purpose: `P${i}` }))
    mockMount({ flights: () => HttpResponse.json({ flights: many, total: 10, total_pages: 1 }) })
    const user = await selectEveryRow()

    await user.selectOptions(screen.getByLabelText('Set purpose for selected flights'), 'Search')

    // Six named, the remaining four counted, so one dialog cannot become a wall
    // of text on a page of a hundred distinct purposes.
    expect(await screen.findByText(/10 will change, replacing: P0 \(1\), P1 \(1\), P2 \(1\), P3 \(1\), P4 \(1\), P5 \(1\), and 4 more\./)).toBeInTheDocument()
  })

  it('renders the flight id cell as a link to the detail route', async () => {
    mockMount()
    renderWithProviders(<FlightsPage />, { role: 'admin' })
    const link = await screen.findByRole('link', { name: 'abcdef12' })
    expect(link).toHaveAttribute('href', '/flights/1')
  })

  it('saving a row unchanged sends nothing, even with a null purpose', async () => {
    let patched = false
    mockMount({
      flights: () => HttpResponse.json({ flights: [{ ...FLIGHTS[0], purpose: null, review_status: 'reviewed' }], total: 1, total_pages: 1 }),
    })
    server.use(http.patch('/api/flights/:id', () => { patched = true; return HttpResponse.json({}) }))
    const { user } = renderWithProviders(<FlightsPage />, { user: { id: 7, username: 'pilot', role: 'pilot', pilot_id: 5 } })
    await screen.findByRole('link', { name: 'Jane Doe' })
    await user.click(screen.getByRole('button', { name: 'Edit' }))
    await user.click(screen.getByTitle('Save'))
    await screen.findByRole('button', { name: 'Edit' })
    expect(patched).toBe(false)
  })

  it('saving a row sends only the changed field', async () => {
    let body = null
    mockMount()
    server.use(http.patch('/api/flights/:id', async ({ request }) => { body = await request.json(); return HttpResponse.json({}) }))
    const { user } = renderWithProviders(<FlightsPage />, { user: { id: 7, username: 'pilot', role: 'pilot', pilot_id: 5 } })
    await screen.findByRole('link', { name: 'Jane Doe' })
    await user.click(screen.getByRole('button', { name: 'Edit' }))
    await user.clear(screen.getByPlaceholderText('sec'))
    await user.type(screen.getByPlaceholderText('sec'), '700')
    await user.click(screen.getByTitle('Save'))
    await waitFor(() => expect(body).toEqual({ duration_seconds: 700 }))
  })

  it('clearing the duration alone sends no PATCH and shows no update message', async () => {
    let patched = false
    mockMount()
    server.use(http.patch('/api/flights/:id', () => { patched = true; return HttpResponse.json({}) }))
    const { user } = renderWithProviders(<FlightsPage />, { user: { id: 7, username: 'pilot', role: 'pilot', pilot_id: 5 } })
    await screen.findByRole('link', { name: 'Jane Doe' })
    await user.click(screen.getByRole('button', { name: 'Edit' }))
    await user.clear(screen.getByPlaceholderText('sec'))
    await user.click(screen.getByTitle('Save'))
    await waitFor(() => expect(screen.queryByTitle('Save')).toBeNull())
    expect(patched).toBe(false)
    expect(screen.queryByText('Flight updated')).toBeNull()
  })

  it('says a reviewed flight is back for review when an edit sends it there', async () => {
    mockMount()
    server.use(http.patch('/api/flights/:id', () => HttpResponse.json({ ...FLIGHTS[1], review_status: 'needs_review' })))
    const { user } = renderWithProviders(<FlightsPage />, { user: { id: 7, username: 'pilot', role: 'pilot', pilot_id: 6 } })
    await screen.findByRole('link', { name: 'Bob Roy' })
    await user.click(screen.getByRole('button', { name: 'Edit' }))
    await user.clear(screen.getByPlaceholderText('sec'))
    await user.type(screen.getByPlaceholderText('sec'), '700')
    await user.click(screen.getByTitle('Save'))
    expect(await screen.findByText(/back for review.*does not count toward currency until reviewed/i)).toBeInTheDocument()
  })

  it('keeps the plain message when the flight stays where it was', async () => {
    mockMount()
    server.use(http.patch('/api/flights/:id', () => HttpResponse.json({ ...FLIGHTS[0], duration_seconds: 700 })))
    const { user } = renderWithProviders(<FlightsPage />, { user: { id: 7, username: 'pilot', role: 'pilot', pilot_id: 5 } })
    await screen.findByRole('link', { name: 'Jane Doe' })
    await user.click(screen.getByRole('button', { name: 'Edit' }))
    await user.clear(screen.getByPlaceholderText('sec'))
    await user.type(screen.getByPlaceholderText('sec'), '700')
    await user.click(screen.getByTitle('Save'))
    expect(await screen.findByText('Flight updated')).toBeInTheDocument()
  })

  describe('bulk action gating', () => {
    async function selectRowsWith(permissions) {
      mockMount()
      const { user } = renderWithProviders(<FlightsPage />, { role: 'supervisor', permissions })
      await user.click(await screen.findByLabelText('Select all flights on this page'))
      await screen.findByText(/\d+ selected/)
    }
    const bar = {
      reassign: () => screen.queryByLabelText('Reassign pilot for selected flights'),
      purpose: () => screen.queryByLabelText('Set purpose for selected flights'),
      reviewed: () => screen.queryByRole('button', { name: 'Mark reviewed' }),
      remove: () => screen.queryByRole('button', { name: 'Delete' }),
    }

    it('shows every action to a default supervisor', async () => {
      await selectRowsWith()
      for (const control of Object.values(bar)) expect(control()).toBeInTheDocument()
    })

    it('hides bulk delete unless flights.delete is All', async () => {
      await selectRowsWith({ 'flights.delete': 'own' })
      expect(bar.remove()).toBeNull()
      expect(bar.reviewed()).toBeInTheDocument()
    })

    it('hides reassign and set purpose unless flights.edit is All', async () => {
      await selectRowsWith({ 'flights.edit': 'own' })
      expect(bar.reassign()).toBeNull()
      expect(bar.purpose()).toBeNull()
      expect(bar.reviewed()).toBeInTheDocument()
      expect(bar.remove()).toBeInTheDocument()
    })
  })
})
