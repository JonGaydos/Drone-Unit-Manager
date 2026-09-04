import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'
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
const PILOTS = [{ id: 5, full_name: 'Jane Doe', is_active: true }, { id: 6, full_name: 'Bob Roy', is_active: true }]
const VEHICLES = [{ id: 2, nickname: 'Falcon', model: 'Mavic 3' }, { id: 3, nickname: 'Hawk', model: 'X10' }]
const PURPOSES = [{ id: 1, name: 'Patrol' }, { id: 2, name: 'Search' }]

function mockMount(overrides = {}) {
  const base = {
    flights: () => HttpResponse.json({ flights: FLIGHTS, total: FLIGHTS.length, total_pages: 1 }),
    pilots: () => HttpResponse.json(PILOTS),
    vehicles: () => HttpResponse.json(VEHICLES),
    purposes: () => HttpResponse.json(PURPOSES),
    count: () => HttpResponse.json({ count: 1 }),
    ...overrides,
  }
  server.use(
    http.get('/api/flights', base.flights),
    http.get('/api/pilots', base.pilots),
    http.get('/api/vehicles', base.vehicles),
    http.get('/api/flights/purposes/list', base.purposes),
    http.get('/api/flights/count', base.count),
    http.get('/api/batteries', () => HttpResponse.json([])),
    http.get('/api/sensors', () => HttpResponse.json([])),
    http.get('/api/attachments', () => HttpResponse.json([])),
  )
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

  it('narrows the visible rows with the search box', async () => {
    mockMount()
    const { user } = renderWithProviders(<FlightsPage />, { role: 'admin' })

    await screen.findByRole('link', { name: 'Jane Doe' })
    await user.type(screen.getByPlaceholderText('Search flights...'), 'Bob')

    expect(screen.queryByRole('link', { name: 'Jane Doe' })).toBeNull()
    expect(screen.getByRole('link', { name: 'Bob Roy' })).toBeInTheDocument()
  })

  it('fires the filtered request with the right query when the status filter changes', async () => {
    // Use a pilot so per-row status badges render as plain text, leaving the
    // status-filter "Reviewed" toggle as the only button with that name.
    server.use(http.get('/api/auth/me', () => HttpResponse.json({ id: 7, username: 'pilot', role: 'pilot' })))
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

  it('hides bulk-selection checkboxes from a pilot but shows them to a supervisor', async () => {
    server.use(http.get('/api/auth/me', () => HttpResponse.json({ id: 7, username: 'pilot', role: 'pilot' })))
    mockMount()
    const { unmount } = renderWithProviders(<FlightsPage />, { role: 'pilot' })
    expect(await screen.findByRole('link', { name: 'Jane Doe' })).toBeInTheDocument()
    expect(screen.queryByLabelText('Select all flights on this page')).toBeNull()
    unmount()

    server.use(http.get('/api/auth/me', () => HttpResponse.json({ id: 8, username: 'sup', role: 'supervisor' })))
    mockMount()
    renderWithProviders(<FlightsPage />, { role: 'supervisor' })
    expect(await screen.findByRole('link', { name: 'Jane Doe' })).toBeInTheDocument()
    expect(screen.getByLabelText('Select all flights on this page')).toBeInTheDocument()
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
    let bulkBody = null
    mockMount()
    server.use(http.post('/api/flights/bulk-update', async ({ request }) => {
      bulkBody = await request.json()
      return HttpResponse.json({ updated: bulkBody.flight_ids.length })
    }))
    const { user } = renderWithProviders(<FlightsPage />, { role: 'supervisor' })

    await screen.findByRole('link', { name: 'Jane Doe' })
    // Select all rows on the page.
    await user.click(screen.getByLabelText('Select all flights on this page'))
    expect(await screen.findByText('2 selected')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Mark reviewed' }))

    await screen.findByRole('link', { name: 'Jane Doe' })  // reloaded
    expect(bulkBody.flight_ids.sort()).toEqual([1, 2])
    expect(bulkBody.review_status).toBe('reviewed')
    expect(bulkBody.pilot_confirmed).toBe(true)
  })

  it('renders the flight id cell as a link to the detail route', async () => {
    mockMount()
    renderWithProviders(<FlightsPage />, { role: 'admin' })
    const link = await screen.findByRole('link', { name: 'abcdef12' })
    expect(link).toHaveAttribute('href', '/flights/1')
  })
})
