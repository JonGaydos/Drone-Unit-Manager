import { describe, it, expect } from 'vitest'
import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'
import CheckoutsPage from './CheckoutsPage'

// Mount endpoints (Promise.all in load(), both .catch -> []):
//   GET /equipment-checkouts
//   GET /pilots
// Check-out modal additionally loads the selected type's endpoint (default /vehicles).
// Check-out action: POST /equipment-checkouts
const CHECKOUTS = [
  { id: 1, entity_type: 'vehicle', entity_id: 10, entity_name: 'DJI Mavic 3 (Falcon)', checked_out_by_name: 'Ada Lovelace', checked_out_at: '2026-06-01T10:00:00', expected_return: '2026-06-10', checked_in_at: null },
]
const PILOTS = [
  { id: 5, first_name: 'Ada', last_name: 'Lovelace', status: 'active' },
]
const VEHICLES = [
  { id: 10, manufacturer: 'DJI', model: 'Mavic 3', nickname: 'Falcon' },
]

function mockMount(overrides = {}) {
  const base = {
    checkouts: () => HttpResponse.json(CHECKOUTS),
    pilots: () => HttpResponse.json(PILOTS),
    vehicles: () => HttpResponse.json(VEHICLES),
    ...overrides,
  }
  server.use(
    http.get('/api/equipment-checkouts', base.checkouts),
    http.get('/api/pilots', base.pilots),
    http.get('/api/vehicles', base.vehicles),
  )
}

describe('CheckoutsPage', () => {
  it('renders without crashing', async () => {
    mockMount()
    renderWithProviders(<CheckoutsPage />, { role: 'admin' })
    expect(await screen.findByRole('heading', { name: /Equipment Checkouts/ })).toBeInTheDocument()
  })

  it('renders active checkout rows from a populated payload', async () => {
    mockMount()
    renderWithProviders(<CheckoutsPage />, { role: 'admin' })
    expect(await screen.findByText('Currently Out (1)')).toBeInTheDocument()
    // The active row appears in both the "Currently Out" and (default) History tables.
    expect(screen.getAllByText('DJI Mavic 3 (Falcon)').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Ada Lovelace').length).toBeGreaterThanOrEqual(1)
  })

  it('shows the empty state when nothing is checked out', async () => {
    mockMount({ checkouts: () => HttpResponse.json([]) })
    renderWithProviders(<CheckoutsPage />, { role: 'admin' })
    expect(await screen.findByText('Nothing checked out.')).toBeInTheDocument()
  })

  it('falls back to the empty state when /equipment-checkouts 500s', async () => {
    // load() .catch -> [] so empty UI renders rather than crashing.
    mockMount({ checkouts: () => HttpResponse.json({ detail: 'boom' }, { status: 500 }) })
    renderWithProviders(<CheckoutsPage />, { role: 'admin' })
    expect(await screen.findByText('Nothing checked out.')).toBeInTheDocument()
  })

  it('checks out an item and fires POST /equipment-checkouts with the captured body', async () => {
    let captured = null
    mockMount({ checkouts: () => HttpResponse.json([]) })
    server.use(
      http.post('/api/equipment-checkouts', async ({ request }) => {
        captured = await request.json()
        return HttpResponse.json({ id: 2, ...captured })
      }),
    )

    const { user } = renderWithProviders(<CheckoutsPage />, { role: 'admin' })
    await screen.findByText('Nothing checked out.')

    await user.click(screen.getByRole('button', { name: /Check Out/ }))
    const dialog = await screen.findByRole('dialog')

    // Item options load from /vehicles once the modal opens.
    await within(dialog).findByRole('option', { name: 'DJI Mavic 3 (Falcon)' })
    // Modal selects (Type, Item, Pilot) lack label/for association; target by order.
    const [, itemSelect, pilotSelect] = within(dialog).getAllByRole('combobox')
    await user.selectOptions(itemSelect, '10')
    await user.selectOptions(pilotSelect, '5')
    await user.click(within(dialog).getByRole('button', { name: 'Check Out' }))

    await screen.findByText('Nothing checked out.')
    expect(captured).toMatchObject({ entity_type: 'vehicle', entity_id: 10, checked_out_by_id: 5 })
  })

  it('hides the history delete control for a non-supervisor (pilot)', async () => {
    server.use(http.get('/api/auth/me', () => HttpResponse.json({ id: 3, username: 'p', role: 'pilot' })))
    // A returned record so the History table has a row to carry the delete action.
    const RETURNED = [{ id: 2, entity_type: 'vehicle', entity_id: 11, entity_name: 'DJI Air 2S', checked_out_by_name: 'Ada Lovelace', checked_out_at: '2026-05-01T10:00:00', checked_in_at: '2026-05-02T10:00:00', checked_in_by_name: 'Ada Lovelace' }]
    mockMount({ checkouts: () => HttpResponse.json(RETURNED) })
    const { container, user } = renderWithProviders(<CheckoutsPage />, { role: 'pilot' })
    await screen.findByText('Nothing checked out.')
    await user.click(screen.getByLabelText(/Show returned/))
    expect(await screen.findByText('DJI Air 2S')).toBeInTheDocument()
    // The delete (Trash) icon button is supervisor-only; absent for a pilot.
    expect(container.querySelector('button.hover\\:text-destructive')).toBeNull()
  })
})
