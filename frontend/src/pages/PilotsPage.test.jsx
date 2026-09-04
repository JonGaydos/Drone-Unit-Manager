import { describe, it, expect } from 'vitest'
import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'
import PilotsPage from './PilotsPage'

// Mount endpoints:
//   GET /pilots   (array; primary, failure -> inline red banner with err.message)
// Create flow: POST /pilots (supervisor-gated "Add Pilot" button + modal)
const PILOTS = [
  { id: 1, first_name: 'Ada', last_name: 'Lovelace', full_name: 'Ada Lovelace', email: 'ada@unit.gov', badge_number: 'A-1', status: 'active' },
  { id: 2, first_name: 'Grace', last_name: 'Hopper', full_name: 'Grace Hopper', email: 'grace@unit.gov', badge_number: 'A-2', status: 'inactive' },
]

function mockMount(overrides = {}) {
  const base = {
    pilots: () => HttpResponse.json(PILOTS),
    ...overrides,
  }
  server.use(http.get('/api/pilots', base.pilots))
}

describe('PilotsPage', () => {
  it('renders without crashing', async () => {
    mockMount()
    renderWithProviders(<PilotsPage />, { role: 'admin' })
    expect(await screen.findByRole('link', { name: /Ada Lovelace/ })).toBeInTheDocument()
  })

  it('loads and renders pilot rows from a populated payload', async () => {
    mockMount()
    renderWithProviders(<PilotsPage />, { role: 'admin' })
    expect(await screen.findByRole('link', { name: /Ada Lovelace/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Grace Hopper/ })).toBeInTheDocument()
    expect(screen.getByText('A-1')).toBeInTheDocument()
  })

  it('shows the empty state when there are no pilots', async () => {
    mockMount({ pilots: () => HttpResponse.json([]) })
    renderWithProviders(<PilotsPage />, { role: 'admin' })
    expect(await screen.findByText('No pilots found')).toBeInTheDocument()
  })

  it('shows the inline error banner when the pilots endpoint 500s', async () => {
    mockMount({ pilots: () => HttpResponse.json({ detail: 'kaboom' }, { status: 500 }) })
    renderWithProviders(<PilotsPage />, { role: 'admin' })
    // Page renders err.message in a red banner; empty table also shows.
    expect(await screen.findByText('No pilots found')).toBeInTheDocument()
    expect(screen.getByText(/kaboom|HTTP 500|500/)).toBeInTheDocument()
  })

  it('creates a pilot via the modal and fires POST /pilots with the captured body', async () => {
    let captured = null
    mockMount({
      pilots: () => HttpResponse.json(PILOTS),
    })
    server.use(
      http.post('/api/pilots', async ({ request }) => {
        captured = await request.json()
        return HttpResponse.json({ id: 99, ...captured })
      }),
    )

    const { user } = renderWithProviders(<PilotsPage />, { role: 'admin' })
    await screen.findByRole('link', { name: /Ada Lovelace/ })

    await user.click(screen.getByRole('button', { name: /Add Pilot/ }))
    const dialog = await screen.findByRole('dialog')

    await user.type(within(dialog).getByLabelText('First Name'), 'Katherine')
    await user.type(within(dialog).getByLabelText('Last Name'), 'Johnson')
    await user.type(within(dialog).getByLabelText('Email'), 'kj@unit.gov')
    await user.click(within(dialog).getByRole('button', { name: 'Add Pilot' }))

    await screen.findByRole('link', { name: /Ada Lovelace/ })
    expect(captured).toMatchObject({ first_name: 'Katherine', last_name: 'Johnson', email: 'kj@unit.gov' })
  })

  // "Counts towards unit totals" is deliberately not the same question as
  // Status. Someone who leaves the unit goes inactive but their flights were
  // still the unit's work; a vendor or guest operator's never were.
  describe('counts towards unit totals', () => {
    async function openTheAddForm() {
      let captured = null
      mockMount({ pilots: () => HttpResponse.json(PILOTS) })
      server.use(
        http.post('/api/pilots', async ({ request }) => {
          captured = await request.json()
          return HttpResponse.json({ id: 99, ...captured })
        }),
      )
      const { user } = renderWithProviders(<PilotsPage />, { role: 'admin' })
      await screen.findByRole('link', { name: /Ada Lovelace/ })
      await user.click(screen.getByRole('button', { name: /Add Pilot/ }))
      const dialog = await screen.findByRole('dialog')
      await user.type(within(dialog).getByLabelText('First Name'), 'Katherine')
      await user.type(within(dialog).getByLabelText('Last Name'), 'Johnson')
      return { user, dialog, body: () => captured }
    }

    it('is on for a new pilot', async () => {
      const { user, dialog, body } = await openTheAddForm()

      expect(within(dialog).getByLabelText(/Counts towards unit totals/i)).toBeChecked()
      await user.click(within(dialog).getByRole('button', { name: 'Add Pilot' }))

      expect(body()).toMatchObject({ counts_toward_totals: true })
    })

    it('can be turned off for a vendor without touching their status', async () => {
      const { user, dialog, body } = await openTheAddForm()

      await user.click(within(dialog).getByLabelText(/Counts towards unit totals/i))
      await user.click(within(dialog).getByRole('button', { name: 'Add Pilot' }))

      expect(body()).toMatchObject({ counts_toward_totals: false, status: 'active' })
    })
  })

  it('hides the Add Pilot control for a non-supervisor (pilot)', async () => {
    server.use(http.get('/api/auth/me', () => HttpResponse.json({ id: 3, username: 'p', role: 'pilot' })))
    mockMount()
    renderWithProviders(<PilotsPage />, { role: 'pilot' })
    await screen.findByRole('link', { name: /Ada Lovelace/ })
    expect(screen.queryByRole('button', { name: /Add Pilot/ })).toBeNull()
  })
})
