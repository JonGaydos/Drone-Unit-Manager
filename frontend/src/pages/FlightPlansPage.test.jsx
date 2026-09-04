import { describe, it, expect } from 'vitest'
import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'
import FlightPlansPage from './FlightPlansPage'

// Mount endpoints (Promise.all in load()):
//   GET /flight-plans?...        (array or { plans })
//   GET /pilots /vehicles
//   GET /flight-plans/pending/count  -> { count }
const PLANS = [
  { id: 1, title: 'River Patrol', date_planned: '2026-06-01T10:00:00', pilot_name: 'Jane Doe', vehicle_name: 'Falcon', location: 'River', purpose: 'Patrol', status: 'pending', submitted_by_id: 5 },
  { id: 2, title: 'Search Op', date_planned: '2026-06-02T08:00:00', pilot_name: 'Bob Roy', vehicle_name: 'Hawk', location: 'Woods', purpose: 'Search', status: 'approved', submitted_by_id: 6 },
]

function mockMount(overrides = {}) {
  const base = {
    plans: () => HttpResponse.json(PLANS),
    count: () => HttpResponse.json({ count: 1 }),
    ...overrides,
  }
  server.use(
    http.get('/api/flight-plans/pending/count', base.count),
    http.get('/api/flight-plans', base.plans),
    http.get('/api/pilots', () => HttpResponse.json([{ id: 5, full_name: 'Jane Doe', is_active: true }])),
    http.get('/api/vehicles', () => HttpResponse.json([{ id: 2, nickname: 'Falcon', model: 'Mavic 3' }])),
  )
}

describe('FlightPlansPage', () => {
  it('renders without crashing', async () => {
    mockMount()
    renderWithProviders(<FlightPlansPage />, { role: 'admin' })
    expect(await screen.findByText('River Patrol')).toBeInTheDocument()
  })

  it('loads and renders plan rows from a populated payload', async () => {
    mockMount()
    renderWithProviders(<FlightPlansPage />, { role: 'admin' })
    expect(await screen.findByText('River Patrol')).toBeInTheDocument()
    expect(screen.getByText('Search Op')).toBeInTheDocument()
    expect(screen.getByText('1 Pending')).toBeInTheDocument()
  })

  it('shows the empty state when there are no plans', async () => {
    mockMount({ plans: () => HttpResponse.json([]), count: () => HttpResponse.json({ count: 0 }) })
    renderWithProviders(<FlightPlansPage />, { role: 'admin' })
    expect(await screen.findByText('No flight plans found')).toBeInTheDocument()
  })

  it('falls back to the empty UI when the primary endpoint 500s', async () => {
    // load() swallows the error into a toast; plans stays [] so the empty UI shows.
    mockMount({ plans: () => HttpResponse.json({ detail: 'boom' }, { status: 500 }) })
    renderWithProviders(<FlightPlansPage />, { role: 'admin' })
    expect(await screen.findByText('No flight plans found')).toBeInTheDocument()
  })

  it('fires the filtered request with the right status query', async () => {
    let lastUrl = null
    mockMount({
      plans: ({ request }) => { lastUrl = new URL(request.url); return HttpResponse.json(PLANS) },
    })
    const { user } = renderWithProviders(<FlightPlansPage />, { role: 'admin' })

    await screen.findByText('River Patrol')
    await user.selectOptions(screen.getByRole('combobox'), 'approved')

    await screen.findByText('River Patrol')
    expect(lastUrl.searchParams.get('status')).toBe('approved')
  })

  it('approves a pending plan via POST /flight-plans/:id/approve (supervisor)', async () => {
    let approved = false
    mockMount()
    server.use(http.post('/api/flight-plans/:id/approve', () => { approved = true; return HttpResponse.json({ ok: true }) }))
    const { user } = renderWithProviders(<FlightPlansPage />, { role: 'supervisor' })

    await screen.findByText('River Patrol')
    await user.click(screen.getByTitle('Approve'))           // row action -> confirm dialog
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Approve' }))  // confirm

    await screen.findByText('River Patrol')
    expect(approved).toBe(true)
  })
})
