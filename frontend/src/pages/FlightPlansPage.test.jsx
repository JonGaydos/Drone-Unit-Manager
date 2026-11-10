import { describe, it, expect } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { fleetOptions, pilotOption, vehicleOption } from '@/test/options'
import { renderWithProviders } from '@/test/render'
import FlightPlansPage from './FlightPlansPage'

// Mount endpoints (Promise.all in load()):
//   GET /flight-plans?...        (array or { plans })
//   GET /pilots /vehicles
//   GET /flight-plans/pending/count  -> { count }
const PLANS = [
  { id: 1, title: 'River Patrol', date_planned: '2026-06-01T10:00:00', pilot_id: 5, pilot_name: 'Jane Doe', vehicle_name: 'Falcon', location: 'River', purpose: 'Patrol', status: 'pending', submitted_by_id: 5 },
  { id: 2, title: 'Search Op', date_planned: '2026-06-02T08:00:00', pilot_id: 6, pilot_name: 'Bob Roy', vehicle_name: 'Hawk', location: 'Woods', purpose: 'Search', status: 'approved', submitted_by_id: 6 },
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
    http.get('/api/pilots/options', () => HttpResponse.json([pilotOption(5, 'Jane Doe')])),
    http.get('/api/fleet/options', () => HttpResponse.json(fleetOptions({ vehicles: [vehicleOption({ id: 2, nickname: 'Falcon', model: 'Mavic 3' })] }))),
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

  it('edits a plan in a dialog and sends only the changed fields', async () => {
    let sent = null
    mockMount()
    server.use(http.patch('/api/flight-plans/:id', async ({ request, params }) => {
      sent = { id: params.id, body: await request.json() }
      return HttpResponse.json({ ...PLANS[0], location: 'North field' })
    }))
    const { user } = renderWithProviders(<FlightPlansPage />, { role: 'admin' })
    await screen.findByText('River Patrol')
    await user.click(screen.getAllByRole('button', { name: 'Edit plan' })[0])

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Edit Flight Plan')).toBeInTheDocument()
    expect(within(dialog).getByLabelText('Title *')).toHaveValue('River Patrol')
    expect(within(dialog).getByLabelText('Planned Date/Time *')).toHaveValue('2026-06-01T10:00')
    await user.clear(within(dialog).getByLabelText('Location'))
    await user.type(within(dialog).getByLabelText('Location'), 'North field')
    await user.click(within(dialog).getByRole('button', { name: 'Save Changes' }))

    await waitFor(() => expect(sent).toEqual({ id: '1', body: { location: 'North field' } }))
  })

  it('edit clears an emptied field with null', async () => {
    let body = null
    mockMount()
    server.use(http.patch('/api/flight-plans/:id', async ({ request }) => {
      body = await request.json()
      return HttpResponse.json(PLANS[0])
    }))
    const { user } = renderWithProviders(<FlightPlansPage />, { role: 'admin' })
    await screen.findByText('River Patrol')
    await user.click(screen.getAllByRole('button', { name: 'Edit plan' })[0])
    const dialog = await screen.findByRole('dialog')
    await user.clear(within(dialog).getByLabelText('Purpose'))
    await user.click(within(dialog).getByRole('button', { name: 'Save Changes' }))
    await waitFor(() => expect(body).toEqual({ purpose: null }))
  })

  it('offers Edit only on plans the user may edit', async () => {
    mockMount()
    // A pilot edits only their own plans (flight_plans.edit = own); plan 1 is user 5's.
    renderWithProviders(<FlightPlansPage />, { user: { id: 5, username: 'p', role: 'pilot' } })
    await screen.findByText('River Patrol')
    // Plan 2 is approved and not theirs; plan 1 is pending and theirs.
    expect(screen.getAllByRole('button', { name: 'Edit plan' })).toHaveLength(1)
  })

  it('reopens a denied plan only after confirmation, with a button named Reopen', async () => {
    let body = null
    mockMount({ plans: () => HttpResponse.json([{ ...PLANS[0], status: 'denied', denial_reason: 'Wind' }]) })
    server.use(http.patch('/api/flight-plans/:id', async ({ request }) => {
      body = await request.json()
      return HttpResponse.json({ ...PLANS[0], status: 'pending' })
    }))
    const { user } = renderWithProviders(<FlightPlansPage />, { role: 'admin' })
    await screen.findByText('River Patrol')
    expect(screen.queryByTitle('Edit (Admin Override)')).toBeNull()
    await user.click(screen.getByRole('button', { name: 'Reopen' }))
    expect(body).toBeNull()
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Reopen' }))
    await waitFor(() => expect(body).toEqual({ status: 'pending' }))
  })

  it('offers neither Approve nor Deny on a plan the reviewer submitted', async () => {
    mockMount({ plans: () => HttpResponse.json([{ ...PLANS[0], submitted_by_id: 1 }]) })
    renderWithProviders(<FlightPlansPage />, { role: 'admin' })
    await screen.findByText('River Patrol')
    expect(screen.queryByTitle('Approve')).not.toBeInTheDocument()
    expect(screen.queryByTitle('Deny')).not.toBeInTheDocument()
  })
})
